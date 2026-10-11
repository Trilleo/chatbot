# Deploying the QQ bot

```
push to main ─▶ CI passes ─▶ Deploy workflow
                              ├─ build the bot image ─▶ Huawei SWR  …/chatbot:<commit>
                              ├─ (in parallel) build NapCat ─▶ SWR  …/napcat:<napcat tree hash>,
                              │     only if SWR doesn't have that tag yet (hours the first time)
                              └─ ssh deploy@server <commit>   (key can only run chatbot-deploy)
                                    └─ server pulls from SWR, restarts the bot (NapCat only if
                                       its image changed), waits until healthy, checks the version

QQ servers ◀──▶ napcat (QQ + NapCat) ──reverse WebSocket, token──▶ bot (NoneBot :8080)
                   │ 127.0.0.1:6099 (WebUI: QR login, via SSH tunnel)       │
                   └──────────── internal `onebot` network ────────────────┘
```

- Runs on the same server as the website, as a second Compose project (`chatbot`) in
  `/srv/chatbot`, with the same `deploy` user and SWR organization.
- Nothing is reachable from the internet. The bot's port is only on Docker networks; the
  only host port is NapCat's WebUI on `127.0.0.1:6099`, reached through an SSH tunnel.
- The bot image carries `docker-compose.yml` and the NapCat tag to use, so server config
  ships with each release. Secrets live only in `/srv/chatbot/.env`.
- **NapCat is the QQ login; restarting it is what risks the account.** Its image is tagged
  with the git tree hash of `napcat/`, so a deploy re-creates it only when `napcat/`
  changed. Ordinary deploys restart only the bot, and NapCat reconnects to it on its own
  (every 5 seconds).
- Files here: `server/chatbot-deploy` (runs on the server), `smoke-test.sh` (run by CI).

Placeholders below: `<SERVER_IP>`, `<REGION>` and `<ORG>` as in the website's
`deploy/README.md`.

## One-time setup

The server already has Docker, the `deploy` user (in the `docker` group), its SWR pull
login, and keys-only SSH from the website's setup (its `deploy/README.md` §4). The SWR
push and pull users work for this repo too, since both use the same organization.

### 1. The server (SSH in as root)

```bash
REGION=cn-east-3    # as for the website
ORG=trilleo
install -d -m 755 -o deploy -g deploy /srv/chatbot
echo "swr.$REGION.myhuaweicloud.com/$ORG" > /srv/chatbot/registry
chown deploy:deploy /srv/chatbot/registry
```

**The `.env`.** Copy `.env.example` from this repo to the server, then fill it in:

```powershell
scp .env.example root@<SERVER_IP>:/srv/chatbot/.env
```

```bash
cd /srv/chatbot && sed -i 's/\r$//' .env
chown deploy:deploy .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → ONEBOT_ACCESS_TOKEN
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → NAPCAT_WEBUI_TOKEN
nano .env
```

Set at least `QQ_ACCOUNT` (the bot's QQ number), `ONEBOT_ACCESS_TOKEN`,
`NAPCAT_WEBUI_TOKEN`, `SUPERUSERS` (your own QQ number, e.g. `["12345678"]`), and
`LLM_API_KEY` (a DeepSeek API key: platform.deepseek.com → API keys). Leave `HOST`,
`PORT` and `LOCALSTORE_USE_CWD` as they are: the containers use their own values.

**The deploy script.** From your PC, in this repo (PowerShell):

```powershell
scp deploy/server/chatbot-deploy root@<SERVER_IP>:/tmp/
```

Then on the server:

```bash
cd /tmp && sed -i 's/\r$//' chatbot-deploy   # in case Windows added CRLF
install -o root -g root -m 755 chatbot-deploy /usr/local/bin/
rm chatbot-deploy
sudo -u deploy chatbot-deploy; echo "exit code: $?"
```

It should print the usage message and `exit code: 64`.

### 2. The deploy key

A second key for the `deploy` user, locked to `chatbot-deploy` (the website's key stays
locked to `trilleo-deploy`). On your PC (PowerShell), in a folder outside the repo:

```powershell
mkdir $env:USERPROFILE\chatbot-keys; cd $env:USERPROFILE\chatbot-keys
ssh-keygen -t ed25519 -f chatbot-deploy -C github-actions-chatbot   # press Enter twice: empty passphrase
scp .\chatbot-deploy.pub root@<SERVER_IP>:/tmp/chatbot-deploy.pub
```

On the server, **append** it (`>>`: the file already holds the website's key):

```bash
printf 'command="/usr/local/bin/chatbot-deploy",restrict %s\n' "$(tr -d '\r' < /tmp/chatbot-deploy.pub)" >> /home/deploy/.ssh/authorized_keys
rm /tmp/chatbot-deploy.pub
cat /home/deploy/.ssh/authorized_keys
```

It should show two lines, one per script. Test from your PC:

```powershell
ssh -i .\chatbot-deploy -o IdentitiesOnly=yes deploy@<SERVER_IP> whoami
```

It should print `usage: chatbot-deploy …`, not `deploy`.

### 3. GitHub settings

In this repo, as for the website (see its §6 for why the key goes in through `cmd`):

```powershell
gh variable set SWR_REGISTRY --body "swr.<REGION>.myhuaweicloud.com"
gh variable set SWR_ORG --body "<ORG>"
gh secret set SWR_USERNAME --body "<REGION>@<PUSH_AK>"
gh secret set SWR_PASSWORD                     # paste the push user's long-term password
gh secret set DEPLOY_HOST --body "<SERVER_IP>"
cmd /c "gh secret set DEPLOY_SSH_KEY < %USERPROFILE%\chatbot-keys\chatbot-deploy"
$hostKey = @(ssh-keygen -F <SERVER_IP> | Where-Object { $_ -match ' ssh-ed25519 ' })
if ($hostKey.Count -eq 1) { gh secret set DEPLOY_KNOWN_HOSTS --body $hostKey[0] } else { "Expected 1 ED25519 line, got $($hostKey.Count)" }
gh variable list; gh secret list
```

It should list 2 variables and 5 secrets. Then delete `$env:USERPROFILE\chatbot-keys`.

### 4. First deploy

Push to `main` (or Actions → Deploy → Run workflow). The first run uploads NapCat's
image to SWR, which takes **hours** at ~70 KB/s; the job allows 5.5 hours. If it times
out, run the workflow again: layers already uploaded are skipped.

When it's done, `cd /srv/chatbot && docker compose ps` shows `bot` (healthy) and
`napcat` (running). Then log QQ in: [README.md → First login](../README.md#first-login).

## Day to day

- **Deploy:** push to `main`. A change under `napcat/` restarts QQ; anything else
  restarts only the bot.
- **What's live:** `cat /srv/chatbot/current`.
- **Roll back** (as root; the last 5 bot images are kept, older ones are pulled again):

  ```bash
  docker image ls "$(cat /srv/chatbot/registry)/chatbot"   # available commits
  sudo -u deploy chatbot-deploy <older-commit-sha>
  ```

  Rolling back to a commit with a different `napcat/` restarts QQ, and doesn't undo
  database migrations.

- **Change a setting in `.env`:** edit `/srv/chatbot/.env`, then
  `cd /srv/chatbot && sudo -u deploy docker compose --env-file .env --env-file release.env up -d --force-recreate bot`
  (a plain restart keeps the old values). Changing `ONEBOT_ACCESS_TOKEN` or `QQ_ACCOUNT`
  needs `napcat` re-created too, which restarts QQ.
- **Logs / status:** `cd /srv/chatbot && docker compose ps`, `docker compose logs -f bot`
  (or `napcat`). Docker Compose reads `.env` here on its own; add
  `--env-file .env --env-file release.env` for commands that (re)create containers, so
  they use the released images.
- **Update NapCat:** Dependabot opens a monthly PR for `napcat/Dockerfile`. Read NapCat's
  release notes, merge, and expect a long upload and one QQ restart (quick login, no QR,
  as long as the volumes are intact).

## Troubleshooting

| Symptom                                                   | Likely cause                                                                                                                                                                       |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deploy fails at "Log in to Huawei SWR"                    | `SWR_USERNAME` must be `<REGION>@<AK>`; the password is the long-term hex string.                                                                                                 |
| Deploy fails at "Deploy on the server"                    | As in the website's table: `DEPLOY_KNOWN_HOSTS`, `DEPLOY_SSH_KEY`, or the key's line in `authorized_keys`. A `docker pull` error: the server's SWR pull login expired.              |
| The NapCat job times out                                  | The first upload is hours long; run the workflow again (uploaded layers are kept).                                                                                                |
| Deploy log: `QQ_ACCOUNT must be set in .env` (or another) | `/srv/chatbot/.env` lacks that value.                                                                                                                                              |
| Deploy log: `bot` is `unhealthy`                          | The job log shows the bot's last lines. `ONEBOT_ACCESS_TOKEN must be set`: fill it in `.env`. `Plugins failed to load`: a bad value in `.env` (the lines above name it). Migration errors: `docker compose logs bot`. |
| Bot never answers, `docker compose logs bot` shows no `Bot <QQ> connected` | NapCat isn't logged in (see First login), or the tokens differ: both containers must be re-created after changing it.                                               |
| `napcat` logs ask for a QR code after a restart           | Quick login failed (session expired, or the device changed: hostname, MAC address or volumes). Scan again through the WebUI; don't restart repeatedly.                            |
