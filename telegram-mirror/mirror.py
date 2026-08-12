"""Update mirror bot: parse match info, POST to live_events endpoint."""
path = "/home/openclaw/telegram-mirror/bot.py"
with open(path) as f:
    src = f.read()

# 1. Add helper functions to extract match info
helper_import = '''import asyncio
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError'''

old_import = '''import asyncio
import logging
import os
import re
import sys

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError'''

if old_import not in src:
    print("OLD IMPORT NOT FOUND")
    import sys as _s
    _s.exit(1)
src = src.replace(old_import, helper_import, 1)

# 2. Add INGEST_URL config
old_env = '''LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()'''
new_env = '''LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LIVE_INGEST_URL = os.getenv("LIVE_INGEST_URL", "http://127.0.0.1:8099/lineup_ai/api/live_events/ingest")'''

if old_env not in src:
    print("OLD ENV NOT FOUND")
    import sys as _s
    _s.exit(1)
src = src.replace(old_env, new_env, 1)

# 3. Add helpers before should_forward()
helpers = '''
# Aug 7 2026: Parse "Home — Away" from the message header. footylivebot posts
# events with a header like "Team A — Team B\\n" then the event line.
def extract_match_label(text: str) -> str:
    m = re.search(r"^([^\\n]+?)\\s*[—–-]\\s*([^\\n]+)$", text.split("\\n", 1)[0] if "\\n" in text else text, re.MULTILINE)
    if m:
        return m.group(1).strip() + " — " + m.group(2).strip()
    # Fallback: take first non-empty line
    for line in text.split("\\n"):
        line = line.strip()
        if line:
            return line
    return ""


def parse_match_teams(match_label: str):
    """Split 'Home — Away' into (home, away)."""
    if " — " in match_label:
        h, a = match_label.split(" — ", 1)
        return h.strip(), a.strip()
    if " - " in match_label:
        h, a = match_label.split(" - ", 1)
        return h.strip(), a.strip()
    if " – " in match_label:
        h, a = match_label.split(" – ", 1)
        return h.strip(), a.strip()
    return "", ""


# Aug 7 2026: Extract player + team from event line. Examples:
#   "🔁 Substitution (8 min) — 🔴 K. Kossa-Rienzi (Seattle Sounders)"
#   "🟥 Red card (45 min) —  L. Johnsen (Sporting Kansas City)"
def extract_player_team(event_line: str):
    # Team is in parentheses at end: "(Team Name)"
    m = re.search(r"\\(([^)]+)\\)\\s*$", event_line)
    team = m.group(1).strip() if m else ""
    # Player is everything before the team parens, stripped of leading emoji + dash + spaces
    player_part = event_line
    if m:
        player_part = event_line[:m.start()]
    player_part = re.sub(r"^[🔴🟥🟨🔁⚽\\s—–\\-]+", "", player_part).strip()
    # Drop trailing dash if any
    player_part = re.sub(r"[—–\\-]+$", "", player_part).strip()
    # If "min" suffix, strip
    player_part = re.sub(r"\\s*min\\s*$", "", player_part, flags=re.IGNORECASE).strip()
    return player_part, team


def post_live_event(event_id: str, event_type: str, match_label: str,
                    minute: int, player: str, team: str, raw_text: str,
                    source_message_id: int) -> bool:
    home, away = parse_match_teams(match_label)
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "match_label": match_label,
        "home": home,
        "away": away,
        "minute": minute,
        "player": player,
        "team": team,
        "raw_text": raw_text,
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "source_message_id": source_message_id,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(LIVE_INGEST_URL, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            log.info(f"Live ingest: {body[:120]}")
            return '"ok": true' in body or '"ok":true' in body
    except urllib.error.URLError as e:
        log.error(f"Live ingest failed: {e}")
        return False
    except Exception as e:
        log.error(f"Live ingest error: {type(e).__name__}: {e}")
        return False


'''
# Insert before "def should_forward"
old_marker = "def should_forward(text: str) -> bool:"
if src.count(old_marker) != 1:
    print(f"Marker count: {src.count(old_marker)}")
    import sys as _s
    _s.exit(1)
src = src.replace("def should_forward(text: str) -> bool:", helpers + "def should_forward(text: str) -> bool:", 1)

# 4. Modify handle() — instead of sending to Telegram, parse event + POST
old_handle = '''    async def handle(self, event):
        msg = event.message
        text = msg.text or ""
        try:
            if not should_forward(text):
                log.info(f"Skip msg id={msg.id} (no match): {text[:120]!r}")
                return
            log.info(f"Forward msg id={msg.id} {SOURCE_CHANNEL} -> {TARGET_CHANNEL}: {text[:120]!r}")
            await self.client.send_message(
                self.target,
                text,
                link_preview=False,
            )
            log.info("Status: SUCCESS")
        except FloodWaitError as e:
            log.error(f"FloodWait {e.seconds}s — retrying")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            log.error(f"ERROR: {type(e).__name__}: {e}")'''

new_handle = '''    async def handle(self, event):
        msg = event.message
        text = msg.text or ""
        try:
            if not should_forward(text):
                log.info(f"Skip msg id={msg.id} (no match): {text[:120]!r}")
                return
            # Aug 7 2026: parse event type, minute, player, team.
            # footylivebot messages are typically:
            #   "Team A — Team B\\n🔁 Substitution (8 min) — 🔴 Player Name (Team B)"
            lines = [ln.strip() for ln in text.split("\\n") if ln.strip()]
            if len(lines) < 2:
                log.info(f"Skip msg id={msg.id} (multi-line required): {text[:120]!r}")
                return
            match_label = lines[0]
            event_line = " ".join(lines[1:])  # join event lines (some posts split)
            minute = extract_minute(event_line)
            player, team = extract_player_team(event_line)
            event_id = f"tg-{msg.id}"
            if is_red_card_explicit(text):
                event_type = "red_card"
            elif is_substitution(text):
                event_type = "substitution"
            else:
                event_type = "other"
            log.info(f"Event msg id={msg.id}: type={event_type}, min={minute}, "
                     f"player={player!r}, team={team!r}, match={match_label!r}")
            ok = post_live_event(event_id, event_type, match_label,
                                 minute, player, team, text, msg.id)
            if ok:
                log.info(f"Live event ingested: msg_id={msg.id}")
            else:
                log.warning(f"Live event ingest returned non-ok: msg_id={msg.id}")
        except FloodWaitError as e:
            log.error(f"FloodWait {e.seconds}s — retrying")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            log.error(f"ERROR: {type(e).__name__}: {e}")'''

if old_handle not in src:
    print("OLD HANDLE NOT FOUND")
    import sys as _s
    _s.exit(1)
src = src.replace(old_handle, new_handle, 1)

with open(path, "w") as f:
    f.write(src)
print("OK")