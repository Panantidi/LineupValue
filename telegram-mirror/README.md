# Telegram Channel Mirror

Listens to **@FormAlert_XI** and re-publishes only
the text of each message to **@lineupvalue_live**.
No buttons, no formatting entities, no event filtering.

Forwards every text-only message from source to target.

## Setup

### 1. Credentials

Edit `.env` (already filled with API_ID and API_HASH):

```
API_ID=38491453
API_HASH=6755e94fb5c0f1079382c8941e6de002
SOURCE_CHANNEL=FormAlert_XI
TARGET_CHANNEL=lineupvalue_live
```

### 2. First-time login (interactive)

You need to authenticate once. Either:

**Option A: Interactive login over SSH**

```bash
ssh -p 2091 openclaw@212.193.4.121
cd /home/openclaw/telegram-mirror
./venv/bin/python -u bot.py
```

You'll be prompted for:
1. Your phone number (international format, e.g. +79991234567)
2. The login code from Telegram

After successful login, `session.session` is saved and the bot will
auto-start without prompting next time.

**Option B: String session (no interactive login)**

Generate a string session on any machine with Telethon installed:

```bash
pip install telethon
python3 -c "
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
api_id = 38491453
api_hash = '6755e94fb5c0f1079382c8941e6de002'
client = TelegramClient(StringSession(), api_id, api_hash)
client.start()
print('SESSION_STRING=' + client.session.save())
"
```

Paste the output into `.env`:
```
SESSION_STRING=AgAA...long_string...
```

The bot will use this instead of an interactive login.

### 3. Run

**Manual (foreground)**

```bash
cd /home/openclaw/telegram-mirror
./venv/bin/python -u bot.py
```

**Manual (background)**

```bash
cd /home/openclaw/telegram-mirror
nohup ./venv/bin/python -u bot.py > /tmp/mirror.log 2>&1 &
tail -f /tmp/mirror.log
```

**Systemd (auto-restart)**

```bash
sudo cp telegram-mirror.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-mirror
sudo systemctl start telegram-mirror
sudo journalctl -fu telegram-mirror
```

**Docker**

```bash
cd /home/openclaw/telegram-mirror
docker compose up -d
docker compose logs -f
```

## How it works

```
FormAlert_XI  --(Telethon listener)-->  bot.py  --(send_message)-->  lineupvalue_live
```

For every new message in `@FormAlert_XI`:
1. Telethon catches the NewMessage event
2. Bot reads `msg.text`
3. Sends to target via `client.send_message(target, msg.text, link_preview=False)`
4. No buttons, no formatting, no inline keyboards

## Logs

```
[20:24:29] [INFO] Connecting to 149.154.167.51:443/TcpFull...
[20:24:29] [INFO] Connection complete
[20:25:30] [INFO] Logged in as username (id=...)
[20:25:30] [INFO] Source: FormAlert_XI (id=...)
[20:25:30] [INFO] Target: lineupvalue_live (id=...)
[20:30:15] [INFO] Forward message id=123 from FormAlert_XI -> lineupvalue_live
[20:30:15] [INFO] Status: SUCCESS
```

Errors:
```
[ERROR] FloodWait 60s — retrying
[ERROR] AttributeError: ...
```

## Files

- `bot.py` — main script (~100 lines)
- `.env` — credentials (API_ID, API_HASH, channels)
- `login.sh` — helper for interactive login
- `Dockerfile` — Python 3.12-slim image
- `docker-compose.yml` — restart: always
- `telegram-mirror.service` — systemd unit
- `session.session` — Telethon session (auto-created)

## Notes

- The Telegram account must be a member of `@FormAlert_XI`
- The same account must have permission to post in `@lineupvalue_live`
- Forwards use `send_message` (only text), so all inline buttons / URL buttons / reply markup are dropped
- `link_preview=False` disables URL previews
- 6-hour FloodWait penalty for repeated failed login attempts — keep credentials stable
