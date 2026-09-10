"""
news_notifier.py — Sep 10 2026
Polls the Rotowire soccer RSS feed (https://www.rotowire.com/rss/news.php?sport=SOCCER)
every 60s and sends new items to the LineupValue Telegram channel (@lineupvalue_alert).

Hard rules (per Max, Sep 10 2026):
  - Message MUST NOT contain the word "Rotowire" (or any case-variant / fragment)
    — strip it from title, description, source label, footer, everything.
  - Match the S-XI / P-XI notifier format: a single source label, body, link.

State: data/news_state.json — list of seen GUIDs (per feed URL).
Skip rule: don't re-send items that were already announced.
Backfill rule: on first run, only send items from the last N hours
(configurable via NEWS_BACKFILL_HOURS, default 12) to avoid spamming
the channel with ancient news when the bot first starts.

Restart pattern: bash /home/openclaw/FormAlert/start_news_notifier.sh
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

# === Config ===
FEED_URL = os.environ.get(
    "NEWS_FEED_URL", "https://www.rotowire.com/rss/news.php?sport=SOCCER"
)
API_BASE = os.environ.get("NEWS_API_BASE", "http://127.0.0.1:8099")
SITE_BASE = os.environ.get("NEWS_SITE_BASE", "https://x11radar.ru")
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_INTERVAL_SEC", "60"))
BACKFILL_HOURS = int(os.environ.get("NEWS_BACKFILL_HOURS", "12"))
MAX_TITLE = 120    # max chars in title (Telegram limit 1024 per msg but keep readable)
MAX_BODY = 700    # max chars in body

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state.json"
LOG_PATH = APP_DIR / "data" / "news_notifier.log"

# Word-level filters — strip mentions of "Rotowire" in any case + nearby
# fragments. (Proximity stripping keeps "rotowire.com" from leaking
# through as part of a longer URL or attribution line.)
# Match as whole word, case-insensitive.
_RE_ROTO = re.compile(r"\b[Rr][Oo][Tt][Oo][Ww][Ii][Rr][Ee]\b", re.IGNORECASE)
_RE_ROTO_URL = re.compile(r"\brotowire\.com\b", re.IGNORECASE)
_RE_URL_TAG = re.compile(r"<[^>]+>")  # strip HTML tags from description
_RE_WS = re.compile(r"\s+")
_RE_SENT = re.compile(r"([.!?])\s+")


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def strip_rotowire(text):
    """Remove every mention of Rotowire and any rotowire.com URLs.

    IMPORTANT: \s in Python re matches \\n too — but we want to PRESERVE
    the line breaks that the caller already placed in the text. So we
    only collapse spaces/tabs, not newlines. After collapsing, restore
    newlines that were mangled by joining single-line replacements.
    """
    if not text:
        return ""
    # Protect newlines by replacing them with a placeholder, run the
    # word strip, then restore. This keeps the caller's paragraph
    # structure intact.
    NL = "\x00"  # null byte — not in normal text
    text = text.replace("\n", NL)
    text = _RE_ROTO.sub("", text)
    text = _RE_ROTO_URL.sub("", text)
    # Collapse runs of spaces/tabs only (NOT newlines — they're now \x00)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    # Trim leading/trailing whitespace per line
    text = "\n".join(line.strip() for line in text.split(NL))
    # Restore newlines
    text = text.replace(NL, "\n")
    # Drop empty lines left by removal (lines that were just "Rotowire.")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    return "\n".join(lines).strip()


def clean_html(s):
    """Strip HTML tags, decode entities, normalize whitespace."""
    if not s:
        return ""
    # Strip tags FIRST so we don't lose entity-decoded < > from
    # legitimate text nodes (e.g. "&amp; &lt; &gt;").
    s = _RE_URL_TAG.sub("", s)
    s = unescape(s)
    s = _RE_WS.sub(" ", s).strip()
    return s


def truncate(text, n):
    if len(text) <= n:
        return text
    # Try to truncate at sentence boundary
    cut = text[:n]
    m = list(_RE_SENT.finditer(cut))
    if m:
        last = m[-1]
        return cut[: last.end()].rstrip() + "…"
    # Fall back to word boundary
    if " " in cut:
        return cut.rsplit(" ", 1)[0].rstrip() + "…"
    return cut.rstrip() + "…"


def fetch_feed(url):
    """Fetch RSS feed and return list of dicts: guid, title, link, body, pub_ts.

    Returns [] on any error (logged).
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "LineupValue/1.0 (+https://x11radar.ru)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
    except Exception as e:
        log(f"FETCH ERROR: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except Exception as e:
        log(f"XML parse error: {e}")
        return []

    items = []
    for item in root.findall(".//item"):
        guid_el = item.find("guid")
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")

        guid = (guid_el.text or "").strip() if guid_el is not None else ""
        title = clean_html(title_el.text or "") if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        body = clean_html(desc_el.text or "") if desc_el is not None else ""
        pub_raw = (pub_el.text or "").strip() if pub_el is not None else ""

        # Parse pubDate to epoch (RFC 2822). Best-effort, accept if it fails.
        pub_ts = 0
        if pub_raw:
            try:
                from email.utils import parsedate_to_datetime
                pub_ts = int(parsedate_to_datetime(pub_raw).timestamp())
            except Exception:
                pub_ts = 0

        # Strip rotowire mentions from everything
        title = strip_rotowire(title)
        body = strip_rotowire(body)
        link = strip_rotowire(link)

        if not guid:
            continue

        items.append({
            "guid": guid,
            "title": title,
            "link": link,
            "body": body,
            "pub_raw": pub_raw,
            "pub_ts": pub_ts,
        })

    return items


def load_state():
    if not STATE_PATH.exists():
        return {"seen": [], "last_check": 0}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": [], "last_check": 0}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_PATH)


def build_message(item):
    """Format one news item as a Telegram message.

    Layout (per Max, Sep 10 2026 — no Rotowire mention anywhere):
        📰 Player: Status update
        ⸻
        First 700 chars of the body, sentences preserved.
        <link to full article>
    """
    title = truncate(item.get("title", ""), MAX_TITLE) or "Update"
    body = truncate(item.get("body", ""), MAX_BODY)
    link = item.get("link", "").strip()
    if link and not link.startswith(("http://", "https://")):
        link = "https://" + link

    parts = []
    parts.append(f"📰 {title}")
    if body:
        parts.append("")
        parts.append(body)
    if link:
        # Build safe URL: keep rotowire.com out of visible text by
        # shortening to host + last path segment.
        short = _shorten_url(link)
        parts.append("")
        parts.append(f"🔗 {short}")

    msg = "\n".join(parts).strip()
    # Final safety net — strip any remaining rotowire mention
    msg = strip_rotowire(msg)
    return msg


def _shorten_url(url):
    """Return a short, human-readable form of a URL that does NOT
    contain 'rotowire' in any form.

    Example:
        https://www.rotowire.com/soccer/player/cody-gakpo-26727
        -> rotowire.com/.../cody-gakpo-26727  (BAD, has rotowire)
        -> player/cody-gakpo-26727           (OK)
    """
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        segs = [s for s in path.split("/") if s]
        if not segs:
            return url
        # Drop the first segment if it's the sport (e.g. "soccer")
        if segs[0].lower() in ("soccer", "football", "nba", "nfl", "mlb", "nhl"):
            segs = segs[1:]
        # Take last 2 segments max for readability
        tail = "/".join(segs[-2:]) if segs else ""
        return tail or url
    except Exception:
        return url


def send_telegram(text):
    """Send a message via Telegram Bot HTTP API. parse_mode=HTML.

    Returns True on success.
    """
    if not TG_TOKEN:
        log("WARN: TG_TOKEN empty, skipping send")
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        params = {
            "chat_id": TG_CHAT,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
        data = urllib.parse.urlencode(params, quote_via=urllib.parse.quote).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        if not resp.get("ok"):
            log(f"TG API NOT OK: {resp}")
            return False
        return True
    except Exception as e:
        log(f"TG send error: {e}")
        return False


def process():
    state = load_state()
    seen = set(state.get("seen", []))
    state_changed = False

    items = fetch_feed(FEED_URL)
    if not items:
        return 0

    # Filter to new items + backfill window
    now = time.time()
    backfill_cutoff = now - BACKFILL_HOURS * 3600

    # Sort newest first
    items.sort(key=lambda x: x.get("pub_ts", 0), reverse=True)

    sent = 0
    for item in items:
        guid = item.get("guid", "")
        if not guid:
            continue

        # First-run backfill: only send items from the last BACKFILL_HOURS
        if not state.get("last_check"):
            if item.get("pub_ts", 0) < backfill_cutoff:
                # Skip old items but still mark as seen
                seen.add(guid)
                state_changed = True
                continue

        if guid in seen:
            continue

        # Skip items with no title and no body (almost-empty posts)
        if not item.get("title") and not item.get("body"):
            seen.add(guid)
            state_changed = True
            continue

        msg = build_message(item)
        ok = send_telegram(msg)
        if ok:
            log(f"SENT: guid={guid} title={item.get('title', '')[:50]!r}")
            sent += 1
            seen.add(guid)
            state_changed = True
            # Throttle to avoid hitting Telegram limits
            time.sleep(0.4)
        else:
            log(f"FAILED to send guid={guid}, will retry next cycle")
            # Don't mark as seen — try again next iteration

    state["seen"] = list(seen)[-500:]   # cap to last 500 GUIDs
    state["last_check"] = int(time.time())
    if state_changed:
        save_state(state)
    return sent


def main():
    log(f"news_notifier started (interval={INTERVAL_SEC}s, feed={FEED_URL})")
    while True:
        try:
            n = process()
            if n:
                log(f"cycle: sent {n} news item(s)")
        except Exception as e:
            log(f"CYCLE ERROR: {e}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
