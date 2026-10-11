#!/usr/bin/env bash
# Starts the stack from docker-compose.yml the way the server does (no builds, images
# given) and checks what can be checked without a QQ login:
#   - the bot migrates (tables exist), starts and reports its version on /health;
#   - NapCat's start wrapper wrote the reverse WebSocket config with the token;
#   - the bot's WebSocket refuses a missing or wrong token and accepts the right one;
#   - nothing but NapCat's WebUI (on 127.0.0.1) is published.
# Used by CI (.github/workflows/ci.yml); runs anywhere with Docker:
#   deploy/smoke-test.sh <bot image> <napcat image> <expected version>
set -euo pipefail

bot_image="${1:?usage: smoke-test.sh <bot image> <napcat image> <version>}"
napcat_image="${2:?usage: smoke-test.sh <bot image> <napcat image> <version>}"
version="${3:?usage: smoke-test.sh <bot image> <napcat image> <version>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"

work="$(mktemp -d)"
project="chatbot-smoke-$$"
account=10000
token="smoke-$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"

# Like /srv/chatbot: the compose file alone, .env, and release.env.
cp "$repo/docker-compose.yml" "$work/docker-compose.yml"
sed -e "s/^QQ_ACCOUNT=.*/QQ_ACCOUNT=$account/" \
	-e "s/^ONEBOT_ACCESS_TOKEN=.*/ONEBOT_ACCESS_TOKEN=$token/" \
	-e "s/^NAPCAT_WEBUI_TOKEN=.*/NAPCAT_WEBUI_TOKEN=smoke-webui/" \
	-e "s/^SUPERUSERS=.*/SUPERUSERS=[\"20000\"]/" \
	"$repo/.env.example" >"$work/.env"
printf 'BOT_IMAGE=%s\nNAPCAT_IMAGE=%s\n' "$bot_image" "$napcat_image" >"$work/release.env"
compose=(docker compose --project-name "$project" --project-directory "$work"
	--env-file "$work/.env" --env-file "$work/release.env")

cleanup() {
	status=$?
	if [[ $status -ne 0 ]]; then
		"${compose[@]}" ps --all || true
		"${compose[@]}" logs --tail 80 || true
	fi
	"${compose[@]}" down --volumes --timeout 5 >/dev/null 2>&1 || true
	rm -rf "$work"
	exit "$status"
}
trap cleanup EXIT

fail() {
	echo "::error::$*" >&2
	exit 1
}

echo "==> Starting the stack"
"${compose[@]}" up --detach --no-build --wait --wait-timeout 120

echo "==> Bot health and version"
live="$("${compose[@]}" exec -T bot python -c \
	"import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5))['version'])")"
[[ "$live" == "$version" ]] || fail "/health reports version '$live', expected '$version'"

echo "==> Database migrated into the volume"
"${compose[@]}" exec -T bot python -c "
import sqlite3, sys
db = sqlite3.connect('file:/data/nonebot_plugin_orm/db.sqlite3?mode=ro', uri=True)
tables = {row[0] for row in db.execute(\"select name from sqlite_master where type = 'table'\")}
missing = {'alembic_version', 'llm_chat_message', 'llm_chat_session'} - tables
sys.exit(f'missing tables: {sorted(missing)}' if missing else 0)
" || fail "the database in /data isn't migrated"

echo "==> NapCat's reverse WebSocket config"
config="$("${compose[@]}" exec -T napcat cat "/app/napcat/config/onebot11_$account.json")"
client="$(jq -c '.network.websocketClients[0]' <<<"$config")"
[[ "$(jq -r .url <<<"$client")" == "ws://bot:8080/onebot/v11/ws" ]] || fail "wrong URL: $client"
[[ "$(jq -r .token <<<"$client")" == "$token" ]] || fail "the token isn't the one from .env"
[[ "$(jq -r .enable <<<"$client")" == "true" ]] || fail "the connection isn't enabled"

echo "==> WebSocket access token"
# From inside the bot container: a raw WebSocket handshake, so no client library needed.
handshake() {
	"${compose[@]}" exec -T bot python - "$1" <<'PY'
import base64, os, socket, sys

token = sys.argv[1]
headers = [
    "GET /onebot/v11/ws HTTP/1.1",
    "Host: bot:8080",
    "Upgrade: websocket",
    "Connection: Upgrade",
    "Sec-WebSocket-Key: " + base64.b64encode(os.urandom(16)).decode(),
    "Sec-WebSocket-Version: 13",
    "X-Self-ID: 10000",
    "X-Client-Role: Universal",
]
if token:
    headers.append("Authorization: Bearer " + token)
with socket.create_connection(("127.0.0.1", 8080), timeout=5) as conn:
    conn.sendall(("\r\n".join(headers) + "\r\n\r\n").encode())
    print(conn.recv(1024).split(b" ")[1].decode())
PY
}
[[ "$(handshake "")" == "403" ]] || fail "a handshake without a token wasn't refused"
[[ "$(handshake "wrong-token")" == "403" ]] || fail "a handshake with a wrong token wasn't refused"
[[ "$(handshake "$token")" == "101" ]] || fail "a handshake with the right token was refused"

echo "==> Published ports"
published="$(docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}} {{.Ports}}' |
	grep -oE '[0-9.:\[\]]+->[0-9]+/tcp' | sort -u | tr '\n' ' ')"
[[ "$published" == "127.0.0.1:6099->6099/tcp " ]] ||
	fail "published ports should be only 127.0.0.1:6099->6099/tcp, got: $published"

echo "==> Smoke test passed"
