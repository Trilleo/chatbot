# chatbot

A QQ bot on a normal QQ alt account: [NapCat](https://napneko.github.io/) runs QQ
headless and speaks OneBot v11; [NoneBot2](https://nonebot.dev/) runs the bot's
features as plugins. Both run in Docker Compose on the website's server.

```
QQ ◀──▶ napcat ──reverse WebSocket (token)──▶ bot (NoneBot, FastAPI driver)
         └ WebUI on 127.0.0.1:6099 only        └ src/plugins/<feature>/
```

Status: **Phase 2**: LLM chat in private messages with friends (DeepSeek), plus `/ping`.

- Deploying and the server: [deploy/README.md](deploy/README.md).
- Working on the code (conventions, adding a plugin): [CLAUDE.md](CLAUDE.md).

## Using the bot

Message the bot privately from an account on its **friend list**; anything that isn't a
command goes to the model (temporary chats started from groups, and groups, are ignored
for now). Replies come in one or more messages after a short random pause.

| Command                        | What it does                                              |
| ------------------------------ | --------------------------------------------------------- |
| `/清空` (`/clear`)             | Forget this chat's context.                               |
| `/人设` (`/persona`)           | List personas; `/人设 brief` switches (kept per chat).    |
| `/设置` (`/settings`)          | Model, persona, and how much context is remembered.       |
| `/ping`                        | `pong`: the chain works. `/echo <text>`: superusers only. |

The bot remembers the last `LLM_CONTEXT_MAX_MESSAGES` messages per chat (about
`LLM_CONTEXT_MAX_TOKENS` tokens), in its database, so restarts and deploys keep them.
Personas are files in `src/plugins/llm_chat/personas/`: a `> description` line, then the
system prompt. A new file is a new persona (after a deploy).

## Layout

```
bot.py                     NoneBot entrypoint: migrates, then runs (`python bot.py orm …`
                           runs migration commands)
src/plugins/<name>/        one folder per feature, each with its own config.py
  llm_chat/                private chat with the LLM: commands, ORM models, personas/
  ping/                    /ping, /echo (superusers): checks the whole chain
  status/                  GET /health (container health check, deploy check)
src/llm/                   LLM chat core without NoneBot: provider (OpenAI-compatible),
                           context window, reply splitter, paced sending, personas
migrations/versions/       database migrations (Alembic, via nonebot-plugin-orm)
tests/                     pytest + nonebug
docker-compose.yml         the stack (used as-is on the server)
docker-compose.override.yml  local builds (read automatically by Docker Compose)
Dockerfile                 the bot image
napcat/                    the NapCat image: upstream image + start.sh (writes the
                           reverse WebSocket config, token included, on every start)
.env.example               every setting; copy to .env
.env.docker                settings the bot image adds (data in the /data volume)
deploy/                    server script, smoke test, runbook
```

## Running locally

Needs [uv](https://docs.astral.sh/uv/). Docker is optional (CI builds and tests the images).

```bash
uv sync
cp .env.example .env    # fill in ONEBOT_ACCESS_TOKEN, and LLM_API_KEY for chat
uv run python bot.py
```

`bot.py` applies database migrations, then starts. The bot listens on `127.0.0.1:8080` (`HOST`/`PORT` in `.env`); `curl
http://127.0.0.1:8080/health` answers `{"status":"ok",…}`. Locally its data (SQLite
database) goes to `./data`.

With Docker, the whole stack, NapCat included:

```bash
docker compose up -d --build
```

### Checks

```bash
uv run ruff format          # or --check
uv run ruff check
uv run mypy
uv run pytest
```

CI also runs these, checks that migrations match the models, builds both images and runs
`deploy/smoke-test.sh` against them.

### Database migrations

`nonebot-plugin-orm` (SQLAlchemy + Alembic), SQLite for now, with one linear history in
`migrations/versions/` for all plugins. Without NB CLI, `bot.py` runs the same commands
as `nb orm`:

```bash
uv run python bot.py orm revision -m "llm_chat: add x"   # after changing models
uv run python bot.py orm upgrade
uv run python bot.py orm check      # does the database match the models?
```

Review a generated migration before committing it. `python bot.py` (and so the Docker
image) applies migrations before starting; the ORM's own startup check would stop to ask
on stdin instead. Write migrations so the
previous release still works with the new schema (a rollback doesn't undo them), and
keep SQL portable so moving to Postgres later is a URL change (`SQLALCHEMY_DATABASE_URL`).

## First login

NapCat's WebUI shows the QR code. It's bound to `127.0.0.1:6099` on the server, never to
a public address; reach it through an SSH tunnel from your PC:

```powershell
ssh -N -L 6099:127.0.0.1:6099 root@<SERVER_IP>
```

Keep that window open, then:

1. Open <http://127.0.0.1:6099/webui> and log in with `NAPCAT_WEBUI_TOKEN` from the
   server's `.env`. (That token only applies when NapCat's config volume is new; after
   that, change it in the WebUI.)
2. Scan the QR code with the QQ app on the phone **signed in to the bot's account**
   (`QQ_ACCOUNT`) and confirm. Alternatively, `docker compose logs napcat` shows the QR code
   in the terminal.
3. Check the chain:

   ```bash
   cd /srv/chatbot && docker compose logs bot | grep connected   # "OneBot V11 | Bot <QQ> connected"
   ```

   Then send the bot a private message `/ping`: it answers `pong`. From an account in
   `SUPERUSERS`, `/echo hello` answers `hello`. Add your account as a friend and send
   it any message to chat.
4. Close the tunnel (Ctrl+C).

### Quick login after restarts

NapCat keeps QQ's login in the `napcat-qq` volume and starts with `ACCOUNT` set, so a
restart logs in again without a QR code. To keep it that way, and keep the account safe:

- **Don't restart NapCat needlessly.** Deploys leave it running unless `napcat/` changed.
  Restart the bot alone with `docker compose restart bot`.
- **Keep the device the same:** the container's hostname and MAC address are fixed in
  `docker-compose.yml`, and the volumes hold the device data. Never delete `napcat-qq`
  (`docker compose down -v` does!) unless you mean to log in from scratch.
- **Keep the login IP stable:** QQ always logs in from the server's address. Don't log the
  bot's account in from other networks meanwhile (the phone app is fine).
- If a restart asks for a QR code again, scan once through the WebUI; repeated restarts
  and logins are what triggers Tencent's risk control.

## Troubleshooting

| Symptom                                                       | Likely cause                                                                                                         |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Bot logs `Authorization Header is invalid` / `Missing …`      | NapCat and the bot have different tokens: re-create both after changing `ONEBOT_ACCESS_TOKEN`.                       |
| Bot logs no `connected` line                                  | NapCat isn't logged in yet, or isn't running: `docker compose logs napcat`.                                          |
| `/ping` gets no answer, but the bot is connected              | The message didn't start with `/` (`COMMAND_START`); check `docker compose logs bot` for the event.                 |
| WebUI: connection refused                                     | The tunnel isn't open, or NapCat isn't running.                                                                      |
| WebUI token rejected                                          | The config volume predates the token in `.env`: use the old token, or read it from `docker compose exec napcat cat /app/napcat/config/webui.json`. |
| Chat replies `机器人这边的配置出了点问题…`                     | `LLM_API_KEY` is missing or rejected, or `LLM_MODEL`/`LLM_BASE_URL` is wrong: `docker compose logs bot` shows the HTTP error. |
| Chat replies `想得太久了…` (timeouts)                          | Thinking took longer than `LLM_TIMEOUT`: raise it, or lower the effort (`LLM_EXTRA_BODY={"reasoning_effort": "low"}`). |
| Chat replies `这个问题我没想好…` often                          | `LLM_MAX_TOKENS` ran out during thinking (`finish_reason=length` in the log): raise it.                              |
| No reply at all to a private message                          | The sender isn't the bot's friend (temporary chats are ignored), or the message starts with `/`.                     |
| Bot exits with `Plugins failed to load: …`                    | That plugin's import failed, usually a bad setting in `.env`: the lines above say which.                             |
| Local run: `ONEBOT_ACCESS_TOKEN must be set`                  | `.env` is missing or the token is empty.                                                                             |
| Local run: `error while attempting to bind on address`        | Something else uses port 8080: set `PORT` in `.env`.                                                                 |
