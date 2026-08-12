"""Simple forwarder with event filter.

Listens to @footylivebot and re-publishes only
selected events to @lineupvalue_live. No buttons,
no formatting entities.

Filter:
- Yellow card (any minute)
- Red card (any minute)
- Substitution up to and including 30 minutes

All other events (goals, later substitutions, score
updates, etc.) are dropped.

Jul 31 2026.
"""
import asyncio
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "footylivebot")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "lineupvalue_live")
SESSION_PATH = os.getenv("SESSION_PATH", "/home/openclaw/telegram-mirror/session")
SESSION_STRING = os.getenv("SESSION_STRING", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LIVE_INGEST_URL = os.getenv("LIVE_INGEST_URL", "http://127.0.0.1:8099/lineup_ai/api/live_events/ingest")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("forwarder")

SUBST_MINUTE_LIMIT = 35

YELLOW_CARD_MARKERS = (
    "\U0001F7E1",
    "\U0001F7E8",
    "Yellow card",
    "yellow card",
    "Желтая карточка",
    "Жёлтая карточка",
)

RED_CARD_MARKERS = (
    "\U0001F7E5",
    "\U0001F7E0",
    "Red card",
    "red card",
    "Красная карточка",
)

SUBST_MARKERS = (
    "\U0001F501",          # 🔁
    "Замена",                 # Russian singular
    "Замены",                 # Russian plural
    "Substit",                # English "Substitution"/"Substituted"
    "substit",
    "Replace",                # "Replaced by"
    "replace",
    "Changes",                # "Changes for [Team]"
)


def is_yellow_card(text: str) -> bool:
    return any(m in text for m in YELLOW_CARD_MARKERS)


def is_red_card_explicit(text: str) -> bool:
    if "\U0001F7E5" in text or "\U0001F7E0" in text:
        return True
    if "Red card" in text or "red card" in text:
        return True
    if "Красная карточка" in text or "красная карточка" in text:
        return True
    return False


def is_substitution(text: str) -> bool:
    return any(m in text for m in SUBST_MARKERS)


def extract_minute(text: str) -> int:
    # Aug 7 2026: match minute marker in all common apostrophe variants:
    # ASCII (\'), right single quote (\u2019), prime (\u2032), modifier letter prime (\u02B9),
    # fullwidth apostrophe (\uFF07), and even the typographic \u2032.
    pat = (
        r"(\d+)"                     # minute digits
        r"(?:\+\d+)?"                # optional added time (45+2)
        r"\s*"
        r"['\u02B9\u2032\u2019\uFF07\u2035\u2033]"  # any apostrophe variant
    )
    m = re.search(pat, text)
    if m:
        return int(m.group(1))
    return -1



# Aug 7 2026: Parse "Home — Away" from the message header. footylivebot posts
# events with a header like "Team A — Team B\n" then the event line.
def extract_match_label(text: str) -> str:
    m = re.search(r"^([^\n]+?)\s*[—–-]\s*([^\n]+)$", text.split("\n", 1)[0] if "\n" in text else text, re.MULTILINE)
    if m:
        return m.group(1).strip() + " — " + m.group(2).strip()
    # Fallback: take first non-empty line
    for line in text.split("\n"):
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


# Aug 12 2026: Extract player + team from event line.
#
# Source format examples (from @footylivebot):
#   Substitution (Russian, multi-line joined with " "):
#     "27': 🔁 Замена в команде **Rio Ave**: 🟢 **Ryan Guilherme** выходит на поле вместо 🔴 **T. Monteiro**"
#   Substitution (English):
#     "🔁 Substitution (8 min) — 🔴 K. Kossa-Rienzi (Seattle Sounders)"
#   Red card (Russian):
#     "47': 🟥 Красная карточка игроку **A. Ntoi** (Rio Ave)"
#   Red card (English):
#     "🟥 Red card (45 min) —  L. Johnsen (Sporting Kansas City)"
#
# For substitutions, return the OUTGOING player (the one who left the pitch) —
# that's the newsworthy fact for squad/injury tracking. Also extract the team
# from the "в команде <TEAM>:" prefix or the trailing "(Team)" parens.
def extract_player_team(event_line: str):
    # Strip markdown bold first so **NAME** → NAME.
    line = event_line.replace("*", "").strip()

    # ---- Substitution (Russian) ----
    # Pattern: "🔁 Замена в команде <TEAM>: 🟢 <IN> выходит на поле вместо 🔴 <OUT>"
    m = re.search(
        r"🔁\s*Замена\s+в\s+команде\s+([^:]+?):\s*"
        r"🟢\s*(.+?)\s+выходит\s+на\s+поле\s+вместо\s+"
        r"🔴\s*(.+?)\s*$",
        line,
    )
    if m:
        return m.group(3).strip(), m.group(1).strip()

    # ---- Substitution (English "Replaced by" / "comes on for") ----
    # Pattern: "... 🔴 <OUT> ... 🟢 <IN> ..." — we want the OUT player.
    m = re.search(
        r"(?:🔴|🟥)?\s*([A-Z][A-Za-zÀ-ÿ'\.\- ]+?)\s+"
        r"(?:is\s+replaced\s+by|comes\s+on\s+for|replaced\s+by)\s+"
        r"(?:🟢|🔁)?\s*([A-Z][A-Za-zÀ-ÿ'\.\- ]+?)\s*$",
        line,
    )
    if m:
        return m.group(1).strip(), ""

    # ---- Generic: trailing "(Team)" parens (works for EN red/yellow cards and some EN subs) ----
    paren_m = re.search(r"\(([^)]+)\)\s*$", line)
    if paren_m:
        team = paren_m.group(1).strip()
        player_part = line[:paren_m.start()]
        # Drop "(N min) —" / "(N min) -" prefix from English "Substitution (8 min) —".
        player_part = re.sub(
            r"^.*?\(\d+\s*(?:\+\d+\s*)?min\)\s*[—–\-:]\s*",
            "",
            player_part,
        ).strip()
        # Strip leading minute marker (e.g. "27':") and surrounding emoji/dashes.
        player_part = re.sub(
            r"^(\d+['\u02B9\u2032\u2019\uFF07]\s*[:：]?\s*)?"
            r"[🔴🟥🟨🔁⚽🟢\s—–\-]+",
            "",
            player_part,
        ).strip()
        # Drop trailing dash and "min" suffix.
        player_part = re.sub(r"[—–\-]+$", "", player_part).strip()
        player_part = re.sub(r"\s*min\s*$", "", player_part, flags=re.IGNORECASE).strip()
        # Drop Russian prefixes (defensive).
        for prefix in (
            "Красная карточка игроку",
            "Жёлтая карточка игроку",
            "Желтая карточка игроку",
            "Замена",
            "Удаление",
        ):
            if player_part.lower().startswith(prefix.lower()):
                player_part = player_part[len(prefix):].strip()
                break
        return player_part, team

    # ---- Fallback: no trailing parens, no Russian pattern — best-effort ----
    player_part = re.sub(r"^[🔴🟥🟨🔁⚽\s—–\-]+", "", line).strip()
    player_part = re.sub(r"[—–\-]+$", "", player_part).strip()
    player_part = re.sub(r"\s*min\s*$", "", player_part, flags=re.IGNORECASE).strip()
    return player_part, ""


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


def should_forward(text: str) -> bool:
    if not text:
        return False
    if is_yellow_card(text):
        log.debug(f"Filter: yellow card match")
        return True
    if is_red_card_explicit(text):
        log.debug(f"Filter: red card match")
        return True
    if is_substitution(text):
        minute = extract_minute(text)
        # Aug 7 2026: Log every substitution attempt so we can audit the 30' cutoff.
        if minute == -1:
            log.info(f"Filter: sub marker found but no minute parsed: {text[:120]!r}")
            return False
        if minute <= SUBST_MINUTE_LIMIT:
            log.info(f"Filter: sub {minute}' <= {SUBST_MINUTE_LIMIT}' PASS: {text[:120]!r}")
            return True
        log.info(f"Filter: sub {minute}' > {SUBST_MINUTE_LIMIT}' SKIP: {text[:120]!r}")
        return False
    return False


class Forwarder:
    def __init__(self):
        if not API_ID or not API_HASH:
            raise RuntimeError("Set API_ID and API_HASH in .env")
        if SESSION_STRING:
            from telethon.sessions import StringSession
            self.client = TelegramClient(
                StringSession(SESSION_STRING),
                API_ID, API_HASH,
                connection_retries=None,
                retry_delay=5,
            )
        else:
            self.client = TelegramClient(
                SESSION_PATH, API_ID, API_HASH,
                connection_retries=None,
                retry_delay=5,
            )
        self.source = None
        self.target = None

    async def start(self):
        await self.client.start()
        me = await self.client.get_me()
        log.info(f"Logged in as {me.username or me.first_name} (id={me.id})")
        self.source = await self.client.get_entity(SOURCE_CHANNEL)
        self.target = await self.client.get_entity(TARGET_CHANNEL)
        log.info(f"Source: {SOURCE_CHANNEL} (id={self.source.id})")
        log.info(f"Target: {TARGET_CHANNEL} (id={self.target.id})")
        log.info(f"Filter: yellow card, red card, sub <= {SUBST_MINUTE_LIMIT}'")

    async def handle(self, event):
        msg = event.message
        text = msg.text or ""
        try:
            if not should_forward(text):
                log.info(f"Skip msg id={msg.id} (no match): {text[:120]!r}")
                return
            # Aug 7 2026: parse event type, minute, player, team.
            # footylivebot messages are typically:
            #   "Team A — Team B\n🔁 Substitution (8 min) — 🔴 Player Name (Team B)"
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
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
            log.error(f"ERROR: {type(e).__name__}: {e}")

    async def run(self):
        await self.start()
        log.info("Listening...")
        @self.client.on(events.NewMessage(chats=self.source))
        async def handler(event):
            await self.handle(event)
        await self.client.run_until_disconnected()


async def main():
    f = Forwarder()
    await f.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped")
        sys.exit(0)