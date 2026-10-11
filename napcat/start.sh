#!/bin/bash
# Writes NapCat's OneBot config for this account, then runs the image's own entrypoint.
#
# NapCat reads onebot11_<account>.json (falling back to onebot11.json), and the
# image's MODE=reverse_ws option can't set a token, so the connection is written here.
# It's rewritten on every start: the environment is the source of truth, and edits to
# the network settings in the WebUI don't survive a restart.
set -euo pipefail

: "${ACCOUNT:?ACCOUNT (QQ_ACCOUNT in .env) must be set}"
: "${ONEBOT_ACCESS_TOKEN:?ONEBOT_ACCESS_TOKEN must be set}"
: "${ONEBOT_URL:?ONEBOT_URL must be set}"
if [[ ! "$ACCOUNT" =~ ^[1-9][0-9]{4,11}$ ]]; then
	echo "ACCOUNT must be a QQ number, got '$ACCOUNT'" >&2
	exit 64
fi

config_dir=/app/napcat/config
mkdir -p "$config_dir"
umask 077
jq -n --arg url "$ONEBOT_URL" --arg token "$ONEBOT_ACCESS_TOKEN" '{
  network: {
    httpServers: [],
    httpSseServers: [],
    httpClients: [],
    websocketServers: [],
    websocketClients: [{
      enable: true,
      name: "nonebot",
      url: $url,
      reportSelfMessage: false,
      messagePostFormat: "array",
      token: $token,
      debug: false,
      heartInterval: 30000,
      reconnectInterval: 5000
    }],
    plugins: []
  },
  musicSignUrl: "",
  enableLocalFile2Url: false,
  parseMultMsg: false
}' >"$config_dir/onebot11_$ACCOUNT.json.tmp"
mv "$config_dir/onebot11_$ACCOUNT.json.tmp" "$config_dir/onebot11_$ACCOUNT.json"

cd /app
exec bash entrypoint.sh
