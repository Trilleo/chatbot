# Project: QQ bot (NapCat + NoneBot2) with LLM chat

## Working style

- Before starting any non-trivial task, ask me clarifying questions about the
  idea and design instead of assuming. Propose a plan and wait for approval.
- Do not commit after changes.
- Keep changes scoped to one task. Summarize what changed and why at the end.
- Work in the phases below and stop for my review at the end of each one. Don't add
  features beyond the current phase; ask when something is ambiguous.
- Keep the documentation current: after every change, check what it affects and
  update it in the same change. That means this file, README.md, deploy/README.md,
  and .env.example (every config key, secrets empty).
- Package names, image names and config keys change: check the current NoneBot2 and
  NapCat docs (or their source) before writing config, not memory.

## Phases

1. Skeleton and smoke test: compose stack, reverse WebSocket with token, `/ping`,
   first-login docs. **Done.**
2. `llm_chat` plugin, private chat only: OpenAI-compatible provider (DeepSeek, no
   fallback; `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, temperature, max tokens),
   per-session sliding-window context (room for summarization later), personas
   switchable by command, QQ-style replies (no streaming, split long replies with
   1–3 s random delays, a small delay before the first), clear/persona/settings
   commands, graceful API errors. **Done.**
3. Groups (only when @mentioned or with a prefix), `admin` plugin (superusers from env,
   per-group switch, user blacklist, in the DB), per-user/per-group rate limits and a
   daily token budget, output filter hook + system-prompt guard, global send throttle.
4. Tool-calling registry for plugins (+ a "current time" demo tool),
   nonebot-plugin-htmlrender helper (long text/code/tables as images), `/status` HTTP
   endpoint for the website.

## Architecture

- Two containers (docker-compose.yml): `napcat` (QQ + NapCat, OneBot v11) connects to
  `bot` (NoneBot2, FastAPI driver) over a reverse WebSocket at
  `ws://bot:8080/onebot/v11/ws`, authenticated with `ONEBOT_ACCESS_TOKEN`. They share
  the internal `onebot` network; `egress` gives both internet access. Nothing is
  published except NapCat's WebUI on 127.0.0.1:6099.
- bot.py: first runs `python bot.py orm upgrade` in a child process (the ORM's own
  startup check would ask on stdin), then `nonebot.init()`, refuses to start without
  `ONEBOT_ACCESS_TOKEN`, registers the OneBot v11 adapter, loads plugins from
  pyproject.toml `[tool.nonebot]` (store plugins by name, plus every folder in
  src/plugins), and exits if any src/plugins folder failed to load (NoneBot would only
  log it). `python bot.py orm <cmd>` runs nonebot-plugin-orm's `nb orm` commands.
- src/plugins/<name>/: one plugin per feature. `__init__.py` with `__plugin_meta__`,
  `config.py` with a pydantic `Config` whose fields carry the plugin's prefix
  (`ping_reply` ⇒ `PING_REPLY`), read with `get_plugin_config(Config)`.
  - ping: `/ping`, `/echo` (superusers). status: `GET /health` (status + version).
  - llm_chat: friends' private messages (`sub_type == "friend"`) that aren't commands
    go to the model; `/clear` `/persona` `/settings` (Chinese aliases 清空/人设/设置).
    One request at a time per session (a lock), so replies stay in order. Errors map
    to short Chinese replies (src/llm/replies.py); details go to the log. models.py
    (`llm_chat_message`: the context; `llm_chat_session`: the chosen persona),
    store.py (SqlContextStore), personas/*.md (`> description`, then the prompt).
- src/llm/: the chat core, importable before `nonebot.init()` (tests import it
  directly; importing anything under src/plugins needs NoneBot initialised).
  - provider.py: `ChatProvider` protocol; `OpenAICompatibleProvider` (official
    `openai` SDK, no streaming) maps failures to `ProviderError` subclasses (timeout,
    rate limit, config, empty reply, unavailable). `LLM_EXTRA_BODY` carries
    provider-specific fields (DeepSeek's `thinking`, `reasoning_effort`).
  - context.py: `ContextStore` protocol, `apply_window` (newest messages within a
    message cap and an estimated-token cap; never starts with an assistant message),
    `Context` (trims the store on every exchange and hands dropped messages to a
    `Summarizer`; the default forgets them), `session_key` (`private:<qq>`,
    `group:<gid>:<qq>`). Tokens are estimated (0.6 per CJK char, 0.3 otherwise).
  - splitter.py (paragraph → line → sentence → hard cut, merged back up to the limit,
    capped parts), sender.py (`send_paced`: random first delay minus the time already
    spent, random gaps), personas.py (parsing; every prompt gets `QQ_STYLE`: plain
    text, no Markdown, short).
- Config: NoneBot reads `.env`, then `.env.{ENVIRONMENT}`; environment variables override
  both, **but only for keys that appear in a dotenv file** (or are built-in). So every key
  goes in .env.example: the bot image ships it as `/app/.env`, its list of known keys,
  and the real values arrive as environment variables from Compose's `env_file: .env`.
  The image sets `ENVIRONMENT=docker`, which adds .env.docker (data dirs under /data,
  `STATUS_VERSION`). Compose forces `HOST=0.0.0.0`/`PORT=8080` in the container.
- Storage: nonebot-plugin-localstore. Locally `LOCALSTORE_USE_CWD=true` (./data,
  ./config, ./cache); in Docker /data (volume `bot-data`) and /tmp/cache.
- Database: nonebot-plugin-orm, SQLite (`/data/nonebot_plugin_orm/db.sqlite3`). One
  linear migration history for all plugins in migrations/versions/ (the ORM's default
  for local plugins); table names are prefixed with the plugin (`llm_chat_*`). Keep the
  schema portable for a later move to Postgres, and compatible with the previous
  release (rollbacks don't downgrade).
- napcat/: `FROM mlikiowa/napcat-docker:<version>` plus start.sh, which writes
  `/app/napcat/config/onebot11_<ACCOUNT>.json` (NapCat's per-account OneBot config; the
  image's `MODE=reverse_ws` can't set a token) on every start, then runs the upstream
  entrypoint. Network edits in the WebUI don't survive a restart.
- Tests: pytest + nonebug. tests/conftest.py initialises NoneBot from .env.example (not the
  developer's .env) with a test token, superuser 10001, temp data dirs and
  `alembic_startup_check=False` (tables created from the models), then loads plugins
  like bot.py. tests/helpers.py builds OneBot events. Chat flow tests monkeypatch
  `llm_chat.chat_provider` with a fake and `llm_chat.pacing` with zero delays.

## Decisions

- Python 3.13 (.python-version), uv (lockfile uv.lock), Ruff (format + lint), mypy strict.
- DeepSeek is the LLM provider, no fallback (OpenAI/Anthropic aren't reachable from the
  server in mainland China). Keep the provider OpenAI-compatible so a local server works
  without code changes. Default model `deepseek-flash` (V4.1-Flash; `deepseek-chat` was
  retired 2026-07-24) with thinking **on** (DeepSeek's default; temperature is ignored
  then, and max tokens include the reasoning, hence 8192 and a 120 s timeout).
- Private chat is for friends only; temporary chats from groups are ignored.
- Context lives in the database (deploys restart the bot often).
- The bot's own text (replies, errors, personas) is Chinese; English for code, docs,
  logs and commit messages.
- The bot logs in to a normal QQ alt account (`QQ_ACCOUNT`, only in .env). Account
  safety comes first:
  - Random small delays before replies (1–3 s, minus thinking time) and between the parts
    of a split reply; at most `LLM_REPLY_MAX_PARTS` messages per reply; a global send
    throttle (Phase 3).
  - No mass messaging, no auto-joining groups.
  - Restart NapCat as rarely as possible: it's the QQ login. Its image tag is
    napcat/'s git tree hash, so deploys only re-create it when napcat/ changes.
    Don't put frequently changing config on the napcat service.
  - Stable device: fixed hostname and MAC address in docker-compose.yml, persistent
    `napcat-qq`/`napcat-config` volumes, stable login IP (the server).
- The status endpoint (Phase 4) will be reached over a Docker network shared with the
  website's stack (no host port).

## Deploy

- Runbook: deploy/README.md. Same server, SWR organization and `deploy` user as the
  website (D:\Development\web, its deploy/README.md), as a second Compose project in
  /srv/chatbot.
- Push to main → CI → Deploy workflow: builds the bot image (`$REGISTRY/chatbot:<sha>`),
  builds and pushes NapCat (`$REGISTRY/napcat:<napcat tree hash>`) only when SWR lacks
  that tag, then SSHes in as `deploy` with a key whose forced command is
  /usr/local/bin/chatbot-deploy. That script takes docker-compose.yml and the NapCat tag
  out of the bot image, writes release.env (BOT_IMAGE, NAPCAT_IMAGE), runs
  `docker compose --env-file .env --env-file release.env up --no-build --wait`, and
  checks /health reports the SHA.
- The server is in mainland China: it can't pull from Docker Hub or ghcr.io. Images come
  from SWR (built by GitHub Actions); uploads to SWR run at ~70 KB/s, so base images
  are pinned and Dependabot proposes updates monthly. NapCat's image is large: a new
  NapCat version means an upload of hours.
- docker-compose.yml is the server's file and must work alone; local builds live in
  docker-compose.override.yml (read automatically by Docker Compose, not shipped).
- Server-only secrets live in /srv/chatbot/.env, never in git or GitHub.
  deploy/server/chatbot-deploy changes need a manual reinstall.
- CI's "Docker images" job builds both images and runs deploy/smoke-test.sh (health and
  version, migrations, NapCat's generated config, token checks on the WebSocket,
  published ports). Docker isn't installed on the dev machine, so images are verified
  in CI.

## Commands

- uv sync / uv run python bot.py
- uv run ruff format / uv run ruff check / uv run mypy / uv run pytest
- uv run python bot.py orm revision -m "..." / orm upgrade / orm check
- Always run format, lint, mypy and tests before declaring a task done.

## Rules

- Type hints everywhere (mypy strict); no `Any` or `type: ignore` without a comment
  explaining why.
- Small functions; short docstrings on public interfaces.
- Secrets live only in .env (gitignored). Ship .env.example only.
- Logging: NoneBot's loguru `logger`. No API keys and no full message contents at INFO
  or above.
- Prefer boring, well-maintained dependencies; versions are pinned in uv.lock.
- Expose no port unless strictly needed; bind anything that must be reachable to
  127.0.0.1 or a Docker network.
- New features need tests (pytest + nonebug). At minimum: the context store, the rate
  limiter, and the message splitter.

## Adding a new plugin

1. Folder src/plugins/<name>/ with `__init__.py` (`__plugin_meta__ = PluginMetadata(...,
   config=Config)`) and `config.py` (`class Config(BaseModel)`, fields prefixed
   `<name>_`). It's loaded automatically (plugin_dirs).
2. Every config key into .env.example, under the plugin's heading (secrets empty).
   Without that, the key can't be set from the environment in Docker.
3. Store plugins (nonebot-plugin-*): `uv add`, then list them in pyproject.toml
   `[tool.nonebot.plugins]` and `require("...")` them before importing.
4. Models: subclass `nonebot_plugin_orm.Model` (explicit `__tablename__`, prefixed with
   the plugin name), then `uv run python bot.py orm upgrade` (revision refuses a
   database behind the latest migration) and
   `uv run python bot.py orm revision -m "<plugin>: ..."`; review
   migrations/versions/<new>.py and commit it.
5. Logic that doesn't need NoneBot goes in a plain package under src/ (like src/llm/),
   so it's easy to test.
6. Tests in tests/test_<name>.py (nonebug's `app.test_matcher`, events from
   tests/helpers.py).
7. Docs: README.md (layout, what the bot does), this file (Architecture), and
   deploy/README.md if the server needs anything.
