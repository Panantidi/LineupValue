"""
news_notifier_ff.py — Sep 13 2026
Polls https://www.futbolfantasy.com/laliga/ultimos-cambios every 60s
and sends each NEW player status change to the LineupValue Telegram
channel @lineupvalue_alert.

The page lists all kinds of events (market values, referee assignments,
picas/estrellas awarded, suspensions, AND player status changes). We
only forward the latter: changes between Doubt / Injured / Tocado
(slight knock) / Disponible / Recuperado.

Format (per Max, Sep 13 2026):
  🔴 ↔️ 🟠 Nteka — Doubt

  Read More (https://www.futbolfantasy.com/laliga/noticias/...)

  If old status is unknown ("está ahora X", "es ahora X"), drop the
  left icon and arrow:
    🟠 Nteka — Doubt
  If the new status is desconocido, we use 🔵 as a fallback marker.

State: data/news_state.json — list of seen event fingerprints
       (source_url + alt text) so the same event is never sent twice.
Backfill: on first run, only send events from the last N hours
          (NEWS_BACKFILL_HOURS, default 24) to avoid spamming.

Replaces the prior Rotowire RSS notifier and the brief /laliga/noticias
notifier (which only sent full articles, not status transitions).

Run: python3 news_notifier_ff.py
Restart: bash /home/openclaw/FormAlert/start_news_notifier_ff.sh
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
    "NEWS_FEED_URL",
    "https://www.futbolfantasy.com/laliga/ultimos-cambios",
)
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_INTERVAL_SEC", "60"))
BACKFILL_HOURS = int(os.environ.get("NEWS_BACKFILL_HOURS", "24"))

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_ff.log"

# === Status vocabulary (Spanish → emoji + display label) ===
# baja   = injured (red)
# duda   = doubt (orange)
# tocado = slight knock (yellow)
# disponible / recuperado = available/recovered (green)
STATUS_ICON_MAP = {
    "dudas_min.png": ("🟠", "Doubt"),
    "lesionados_min.png": ("🔴", "Injured"),
    "tocados_min.png": ("🟡", "Tocado"),
    "icono_big_ok.png": ("🟢", "Available"),
}

# alt text → (new_status_key, old_status_key or None)
# "X pasa de A a B"   → old=A, new=B
# "X está ahora B"    → old=None, new=B
# "X es ahora B"      → old=None, new=B
STATUS_KEYWORD_MAP = {
    "baja": "baja",
    "duda": "duda",
    "disponible": "disponible",
    "recuperado": "recuperado",
    "tocado": "tocado",
    "tocado o al margen": "tocado",
}
STATUS_EMOJI = {
    "baja": "🔴",
    "duda": "🟠",
    "tocado": "🟡",
    "disponible": "🟢",
    "recuperado": "🟢",
    None: "🔵",
}
STATUS_LABEL = {
    "baja": "Injured",
    "duda": "Doubt",
    "tocado": "Tocado",
    "disponible": "Available",
    "recuperado": "Available",
    None: "Unknown",
}

# Reject rows whose icon is one of these (non-status noise)
NOISE_ICONS = {
    "icono_big_prensa.png",  # press news
    "list.png",              # generic list icon
    "icono_big_stats.png",   # stats news
    "icono_big_traspaso.png",  # transfer
}
NOISE_TEXT_PREFIXES = (
    "Picas asignadas",
    "Estrellas asignadas",
    "Árbitro asignado",
    "Valores de mercado",
    "Alineación confirmada",
)

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_RE_ALT = re.compile(r'alt="([^"]+)"')
_RE_ICON = re.compile(r'src="[^"]*/(icono_big_[a-z]+|[a-z_]+_min|list)\.png"')
_RE_HREF = re.compile(r'href="(https?://[^"]+)"')
_RE_EVENT_ROW = re.compile(r'class="col-12 p-0 event-row"')
_RE_EVENT_TIME = re.compile(r'class="event-time"[^>]*>(\d{1,2}):(\d{2})</span>')


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
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_status_alt(alt):
    """Returns (player_name, old_status_key, new_status_key) or None.

    Examples:
      "Nteka pasa de baja a duda" → ("Nteka", "baja", "duda")
      "Eric Garcia está ahora recuperado" → ("Eric Garcia", None, "recuperado")
      "I. Williams está ahora tocado o al margen" → ("I. Williams", None, "tocado")
    """
    s = alt.strip()
    # Pattern 1: "X pasa de A a B"
    m = re.match(
        r"^([A-Za-z][\w\.\- ]+?)\s+pasa\s+de\s+([a-záéíóú ]+?)\s+a\s+([a-záéíóú ]+?)$",
        s, re.IGNORECASE,
    )
    if m:
        name, old_raw, new_raw = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip().lower()
        old_key = STATUS_KEYWORD_MAP.get(_normalise_status(old_raw))
        new_key = STATUS_KEYWORD_MAP.get(_normalise_status(new_raw))
        if new_key:
            return (name, old_key, new_key)
    # Pattern 2: "X está ahora B" / "X es ahora B"
    m = re.match(
        r"^([A-Za-z][\w\.\- ]+?)\s+(?:está ahora|es ahora)\s+(.+?)$",
        s, re.IGNORECASE,
    )
    if m:
        name, new_raw = m.group(1).strip(), m.group(2).strip().lower()
        new_key = STATUS_KEYWORD_MAP.get(_normalise_status(new_raw))
        if new_key:
            return (name, None, new_key)
    return None


def _normalise_status(raw):
    """Match raw text like 'baja' or 'tocado o al margen' against keyword map."""
    if not raw:
        return raw
    if raw in STATUS_KEYWORD_MAP:
        return raw
    # try to find a contained keyword
    for k in STATUS_KEYWORD_MAP:
        if k in raw:
            return k
    return raw


def parse_index(html_str):
    """Yield dicts: {alt, icon, href, hh, mm} per status-change event-row."""
    chunks = _RE_EVENT_ROW.split(html_str)
    # chunks[0] is the preamble, the rest are event-row bodies
    for chunk in chunks[1:]:
        m_alt = _RE_ALT.search(chunk)
        m_icon = _RE_ICON.search(chunk)
        m_href = _RE_HREF.search(chunk)
        m_time = _RE_EVENT_TIME.search(chunk)
        if not (m_alt and m_href):
            continue
        alt = m_alt.group(1)
        href = m_href.group(1)
        icon = m_icon.group(1) + ".png" if m_icon else None
        hh = int(m_time.group(1)) if m_time else None
        mm = int(m_time.group(2)) if m_time else None
        yield {"alt": alt, "icon": icon, "href": href, "hh": hh, "mm": mm}


def is_status_event(item):
    """Filter: only player status changes pass through."""
    # Reject if icon is in known noise set
    if item["icon"] in NOISE_ICONS:
        return False
    # Reject if text starts with known noise prefix
    for p in NOISE_TEXT_PREFIXES:
        if item["alt"].startswith(p):
            return False
    # Reject if no icon AND no status-changing text
    parsed = parse_status_alt(item["alt"])
    if not parsed:
        return False
    # Reject if icon is unknown (e.g. cabeceras for market values)
    if item["icon"] and item["icon"] not in STATUS_ICON_MAP:
        return False
    return True


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def build_message(item):
    name, old_key, new_key = parse_status_alt(item["alt"])
    new_emoji = STATUS_EMOJI.get(new_key, "🔵")
    new_label = STATUS_LABEL.get(new_key, "Unknown")
    # Use alt text as source of truth for the link
    url = item["href"]
    # First line: emojis + name + label
    if old_key and old_key != new_key:
        old_emoji = STATUS_EMOJI.get(old_key, "🔵")
        first = f"{old_emoji} ↔️ {new_emoji} {name} — {new_label}"
    else:
        first = f"{new_emoji} {name} — {new_label}"
    parts = [first, "",
             f'<a href="{html_escape(url)}">Read More ({html_escape(url)})</a>']
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

    seen = set(state.get("seen") or [])
    sent = 0
    first_run = not seen
    accepted = 0
    skipped_old = 0

    # On the very first run, the page lists the last 24h of events. We
    # do NOT want to spam the channel with the entire backlog — instead
    # we mark all of them as seen and start sending only NEW events
    # from now on. (If a user wants the backlog, they can delete
    # data/news_state.json and re-run.)
    if first_run:
        log("  first run: marking all current events as seen (no backfill dump)")
        for item in parse_index(html_str):
            fp = f"{item['href']}::{item['alt']}"
            seen.add(fp)
        state["seen"] = list(seen)[-2000:]
        save_state(state)
        log(f"  seeded state with {len(seen)} fingerprints; no notifications sent")
        return 0

    for item in parse_index(html_str):
        if not is_status_event(item):
            continue
        accepted += 1
        fp = f"{item['href']}::{item['alt']}"
        if fp in seen:
            continue
        msg = build_message(item)
        if send_telegram(msg):
            sent += 1
            seen.add(fp)
            log(f"  SENT: {item['alt']!r}  fp={fp[:80]}")
        else:
            log(f"  send failed for {item['alt']!r}, will retry")
            break

    state["seen"] = list(seen)[-2000:]
    save_state(state)
    log(f"  cycle: accepted={accepted}  sent={sent}  state_size={len(seen)}")
    return sent


def main():
    log("=== news_notifier_ff (status-changes feed) starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    state = load_state()
    log(f"  loaded state: {len(state.get('seen') or [])} seen fingerprints")

    while True:
        try:
            n = process_once(state)
            if n == 0:
                pass  # keep quiet in the log
        except Exception as e:
            log(f"  cycle error: {e!r}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
