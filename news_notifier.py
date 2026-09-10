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


def strip_cta(text):
    """Remove marketing/CTA boilerplate like:
        'Visit Rotowire.com for more analysis on this update.'
        'Read more at ESPN.com for the full story.'
        'Continue reading on BleacherReport.com for more coverage.'
        'For the full report, click here.'
        '.com for more analysis on this update.'   (after URL strip)

    Strategy: process per-sentence (split on . ! ? followed by
    whitespace or end), drop sentences that look like CTAs, rejoin.
    The "what is a CTA?" check is a set of regex patterns.
    """
    if not text:
        return ""

    # Step 1: split into sentences. Period+optional closing-quote +
    # whitespace + uppercase OR end-of-string. Use a capture group
    # around the delimiter so re.split keeps it in the output — we'll
    # reassemble and the whitespace is preserved.
    parts = re.split(r"([.!?]['\"\)\]]*\s+)(?=[A-Z])|([.!?]['\"\)\]]*$)", text)
    # parts is alternating [chunk, delim-or-None, ...]. We want to
    # rebuild the text by keeping non-empty delimiters and the chunks.
    sentences = []
    buf = ""
    for p in parts:
        if p is None:
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
            continue
        buf += p
    if buf.strip():
        sentences.append(buf.strip())

    # Step 2: define CTA detectors
    def is_cta(s):
        s_stripped = s.strip()
        if not s_stripped:
            return False
        # Verb + optional URL token + analysis-type word
        # Examples: "Visit Rotowire.com for more analysis",
        # "Read more on ESPN.com for the full story",
        # "Visit for more analysis" (URL stripped), "Click here for more".
        if re.search(
            r"\b(?:Visit|Read|Click|See|Check\s+out|Continue\s+reading|Find\s+out|Get|"
            r"Learn|Subscribe|Sign\s+up)\b"
            r"(?:\s+\S+?){0,4}?\s+"
            r"(?:for|on|at|with)\s+"
            r"(?:\S+\s+){0,4}?"
            r"(?:analysis|coverage|story|stories|updates?|news|details?|info(?:rmation)?|article|here)\b",
            s_stripped, re.IGNORECASE,
        ):
            return True
        # "for the full story" / "for more coverage" / "read more at" /
        # "continue reading on" etc., bare forms
        if re.search(
            r"\b(?:for\s+(?:more|the\s+full|the\s+rest|additional|complete)\s+"
            r"(?:analysis|coverage|story|stories|updates?|news|details?|info(?:rmation)?|article)"
            r"|continue\s+reading\s+(?:on|at)|read\s+more\s+(?:at|on|here)|"
            r"see\s+more\s+(?:at|on|here)|learn\s+more\s+(?:at|on|here)|"
            r"click\s+here|for\s+more\s+on\s+this|for\s+the\s+latest)\b",
            s_stripped, re.IGNORECASE,
        ):
            return True
        # Bare "Visit.com" / "Read on X" leftover (after URL strip)
        if re.search(
            r"\b(?:Visit|Read|Click|See|Check|Find|Get|Continue|More|Learn)\.?\s*com\b",
            s_stripped, re.IGNORECASE,
        ):
            return True
        # Bare ".com for more analysis" / ".com read more"
        if re.search(r"\.com\b.*?(?:for\s+more|read\s+more|continue)", s_stripped, re.IGNORECASE):
            return True
        return False

    # Step 3: keep non-CTA sentences
    kept = [s for s in sentences if not is_cta(s)]

    # Step 4: rejoin. Use a single space to ensure clean separation
    # (handles cases where the regex split ate a space, or where the
    # sentence end had no whitespace).
    out = " ".join(s for s in kept if s).strip()
    # Cleanup: collapse runs of whitespace, then collapse the
    # period+space+period produced when a CTA sentence is dropped
    # between two kept sentences (e.g. "A. B. Visit X. C." -> "A. C.").
    # Step 4: rejoin. Use a single space to ensure clean separation
    # (handles cases where the regex split ate a space, or where the
    # sentence end had no whitespace).
    out = " ".join(s for s in kept if s).strip()
    # Cleanup: collapse runs of whitespace, then collapse the
    # period+space+period produced when a CTA sentence is dropped
    # between two kept sentences (e.g. "A. B. Visit X. C." -> "A. C.").
    out = re.sub(r"\s+\.", ".", out)   # " ." -> "."
    out = re.sub(r'([\'\"\)\]])\s+\.', r"\1.", out)  # " ." -> "." after quote
    out = re.sub(r"\.{2,}", ".", out)  # ".." -> "."
    out = re.sub(r"\s{2,}", " ", out)
    return out


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

        # Strip rotowire mentions + any CTA/boilerplate ("Visit X for
        # more", "Read on Y", etc.) from title and body. Title is short
        # and unlikely to have CTAs but we still run the strip for
        # safety. Body uses strip_cta which is designed for trailing
        # boilerplate sentences.
        title = clean_html(title_el.text or "") if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        body = clean_html(desc_el.text or "") if desc_el is not None else ""
        pub_raw = (pub_el.text or "").strip() if pub_el is not None else ""

        title = strip_rotowire(title)
        title = strip_cta(title)
        body = strip_cta(strip_rotowire(body))
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

    Layout (per Max, Sep 11 2026 — no Rotowire mention, no third-party
    links anywhere — only the actual news content):
        📰 Player: Status update

        First 700 chars of the body, sentences preserved.
    """
    title = truncate(item.get("title", ""), MAX_TITLE) or "Update"
    body = truncate(item.get("body", ""), MAX_BODY)

    parts = []
    parts.append(f"📰 {title}")
    if body:
        parts.append("")
        parts.append(body)
    # No link line — third-party URLs are not shown in the channel
    # (per Max, Sep 11 2026). The message contains only the news.

    msg = "\n".join(parts).strip()
    # Final safety net — strip any remaining rotowire mention
    msg = strip_rotowire(msg)
    return msg


def _shorten_url(url):
    """Return a short, human-readable form of a URL that does NOT
    contain 'rotowire' in any form. Kept for potential future use
    but no longer called by build_message (Sep 11 2026 — links
    dropped from channel output entirely).

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
    cycle_count = 0
    while True:
        try:
            n = process()
            cycle_count += 1
            # Heartbeat every 5 cycles (~5 min) so we can confirm the
            # loop is alive even when there's no news to send.
            if cycle_count % 5 == 0 or n:
                log(f"cycle {cycle_count}: sent {n} news item(s)")
        except Exception as e:
            log(f"CYCLE ERROR: {e}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
