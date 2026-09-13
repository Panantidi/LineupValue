"""
news_notifier_epl.py — Sep 13 2026
Polls https://starting11.com/press-conferences/premier-league every 60s
and forwards new player status entries to the LineupValue Telegram
channel @lineupvalue_alert.

Each entry on starting11 is shaped like:
  [TAG] Player Name · Team · source label
        "Quote from the press conference / news article"
        ↗ https://source-url

We only forward the categories that match injury / rotation news:
  OUT      -> 🔴 Injured
  DOUBT    -> 🟠 Doubt
  FIT      -> 🟢 Available
  RETURNS  -> 🟢 Available
  (STARTS / RESTED are NOT forwarded — they're not newsworthy here)

Multiple entries that share the same source URL are merged into a
single Telegram message so the reader doesn't get a flood of one-line
posts about the same article.

Format (per Max, Sep 13 2026):
  🔴 Saliba — Injured
  🟠 Mosquera — Doubt

  "William Saliba remains our only other injury issue..."
  "Cristhian Mosquera is also edging closer to a comeback..."

  Source: https://www.arsenal.com/news/...

State: data/news_state_epl.json — list of seen source URLs.

Run: python3 news_notifier_epl.py
Restart: bash /home/openclaw/FormAlert/start_news_notifier_epl.sh
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

# === Config ===
FEED_URL = os.environ.get(
    "NEWS_EPL_FEED_URL",
    "https://starting11.com/press-conferences/premier-league",
)
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_EPL_INTERVAL_SEC", "60"))
HASHTAG = "#England"

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state_epl.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_epl.log"

# Status tag → (emoji, English label)
TAG_MAP = {
    "OUT": ("🔴", "Injured"),
    "DOUBT": ("🟠", "Doubt"),
    "FIT": ("🟢", "Available"),
    "RETURNS": ("🟢", "Available"),
}

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_RE_LI = re.compile(r'<li class="px-4 py-2\.5">(.*?)</li>', re.S)
_RE_TAG = re.compile(r'<span style="color:#[a-f0-9]+">([A-Z]+)</span>')
_RE_PLAYER = re.compile(r'href="/player/([a-z0-9-]+)">([^<]+)</a>')
_RE_TEAM = re.compile(
    r'href="/player/[a-z0-9-]+">[^<]+</a>'
    r'\s*<span class="text-\[10px\][^"]*"[^>]*>'
    r'([^<]+)(?:<!--[^>]*-->)?([^<]*)',
    re.S,
)


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    if not STATE_PATH.exists():
        return {"seen": []}
    try:
        return json.loads(STATE_PATH.read_text("utf-8") or "{}")
    except Exception:
        return {"seen": []}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def fetch(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def text_only(html_str):
    if not html_str:
        return ""
    s = _HTML_TAG.sub(" ", html_str)
    s = unescape(s)
    s = _WS.sub(" ", s).strip()
    return s


def parse_items(html_str):
    """Yield dicts: {tag, name, team, msg, src} per status entry.

    Only entries with a tag in TAG_MAP are returned (OUT/DOUBT/FIT/RETURNS).
    STARTS/RESTED/etc. are dropped here.
    """
    for li in _RE_LI.finditer(html_str):
        block = li.group(1)
        tag_m = _RE_TAG.search(block)
        if not tag_m:
            continue
        tag = tag_m.group(1)
        if tag not in TAG_MAP:
            continue
        name_m = _RE_PLAYER.search(block)
        if not name_m:
            continue
        name = name_m.group(2)
        team_m = _RE_TEAM.search(block)
        team = ""
        if team_m:
            raw = text_only(team_m.group(1) + (team_m.group(2) or ""))
            team = raw.split("·")[0].strip() if raw else ""
        # Source URL = last external href in the block
        ext_links = re.findall(
            r'<a href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.S
        )
        if not ext_links:
            continue
        src, msg_html = ext_links[-1]
        msg = text_only(msg_html).rstrip("↗").rstrip().rstrip('"').rstrip().strip()
        # Trim surrounding " " quotes
        if msg.startswith('"') and msg.endswith('"'):
            msg = msg[1:-1].strip()
        if msg.startswith('“') and msg.endswith('”'):
            msg = msg[1:-1].strip()
        yield {"tag": tag, "name": name, "team": team, "msg": msg, "src": src}


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def build_message(items, src):
    """items: list of {tag, name, team, msg}. All share the same source."""
    # Header lines
    header_lines = []
    seen_lines = set()
    for it in items:
        emoji, label = TAG_MAP[it["tag"]]
        line = f"{emoji} {it['name']} — {label}"
        # Avoid dup if two entries for same player & tag share msg
        if line not in seen_lines:
            header_lines.append(line)
            seen_lines.add(line)
    body_lines = []
    for it in items:
        # Trim very similar quotes (some pressers repeat the same phrase)
        if it["msg"] and it["msg"] not in "\n".join(body_lines):
            body_lines.append(html_escape(it["msg"]))
    parts = list(header_lines)
    if body_lines:
        parts.append("")
        parts.extend(body_lines)
    parts.append("")
    parts.append(f"Source: {html_escape(src)}")
    parts.append(HASHTAG)
    return "\n".join(parts)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    params = {
        "chat_id": TG_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    data = urllib.parse.urlencode(params, quote_via=urllib.parse.quote).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
        return '"ok":true' in body
    except Exception as e:
        log(f"  telegram send failed: {e}")
        return False


def process_once(state):
    try:
        html_str = fetch(FEED_URL)
    except Exception as e:
        log(f"  fetch index failed: {e}")
        return 0

    from collections import defaultdict
    by_src = defaultdict(list)
    for it in parse_items(html_str):
        by_src[it["src"]].append(it)

    seen = set(state.get("seen") or [])
    sent = 0
    is_first_run = not seen

    if is_first_run:
        log("  first run: marking all current sources as seen (no backfill dump)")
        for src in by_src.keys():
            seen.add(src)
        state["seen"] = list(seen)[-1000:]
        save_state(state)
        log(f"  seeded state with {len(seen)} sources; no notifications sent")
        return 0

    for src, items in by_src.items():
        if src in seen:
            continue
        msg = build_message(items, src)
        if send_telegram(msg):
            sent += 1
            seen.add(src)
            log(f"  SENT src={src[-60:]} ({len(items)} entries)")
        else:
            log(f"  send failed for {src}, will retry")
            break

    state["seen"] = list(seen)[-1000:]
    save_state(state)
    log(f"  cycle: sources_now={len(by_src)} sent={sent} state_size={len(seen)}")
    return sent


def main():
    log("=== news_notifier_epl (starting11 Premier League) starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    state = load_state()
    log(f"  loaded state: {len(state.get('seen') or [])} seen sources")

    while True:
        try:
            n = process_once(state)
            if n == 0:
                pass
        except Exception as e:
            log(f"  cycle error: {e!r}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
