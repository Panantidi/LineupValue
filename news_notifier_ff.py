"""
news_notifier_ff.py — Sep 13 2026
Polls https://www.futbolfantasy.com/laliga/noticias every 60s and
sends new items to the LineupValue Telegram channel (@lineupvalue_alert).
Replaces the Rotowire RSS notifier (news_notifier.py) per Max's request.

Each new entry is a news article on futbolfantasy.com. The page is
server-rendered PHP, no JS, no auth. The /laliga/noticias index lists
~100+ recent articles; we extract IDs and titles from the index, then
fetch each article's full body to compose the message.

State: data/news_state.json — list of seen article IDs (string).
Skip rule: don't re-send articles that were already announced.
Backfill rule: on first run, only send articles from the last N hours
(configurable via NEWS_BACKFILL_HOURS, default 12) to avoid spamming
the channel with ancient news.

Hard rules (per Max, Sep 11 2026):
  - Match the S-XI / P-XI notifier format: a single line "⚠️ <title>"
    (HTML bold) + body + (optional) compare link.
  - No mention of futbolfantasy, Rotowire, or any third-party source.
  - Player -> next match URL resolution: if the first player mentioned
    in the title is in our alias layer and the team has a fixture
    today, append a "Home - Away" link to that compare page.

Run: python3 news_notifier_ff.py
Restart pattern: bash /home/openclaw/FormAlert/start_news_notifier_ff.sh
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
    "https://www.futbolfantasy.com/laliga/noticias",
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
MAX_TITLE = 120
MAX_BODY = 700

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_ff.log"

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_RE_URL_LINE = re.compile(
    r"href=\"(https?://(?:www\.)?futbolfantasy\.com/laliga/noticias/(\d+)-([^\"]+))\""
)
_ES_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_RE_ES_DATE = re.compile(
    r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo),?\s+"
    r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del?)\s+(\d{4})"
    r"(?:[^\d]{1,40}(\d{1,2}):(\d{2}))?",
    re.IGNORECASE,
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
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _text(html_str):
    s = _HTML_TAG.sub(" ", html_str or "")
    s = unescape(s)
    s = _WS.sub(" ", s).strip()
    return s


def parse_index(html_str):
    """Return [{id, title, slug, url}] from /laliga/noticias, newest first."""
    seen_in_page = set()
    out = []
    for m in _RE_URL_LINE.finditer(html_str):
        url, nid, slug = m.group(1), m.group(2), m.group(3)
        if nid in seen_in_page:
            continue
        seen_in_page.add(nid)
        end = html_str.find("</a>", m.end())
        if end == -1:
            continue
        block = html_str[m.end():end]
        title_raw = _text(block)
        if not title_raw:
            continue
        out.append({
            "id": nid,
            "title": title_raw,
            "slug": slug,
            "url": url,
        })
    return out


def parse_article(html_str):
    """Extract {h1, entradilla, body, date_str} from a single article page."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html_str, re.S | re.I)
    h1 = _text(m.group(1)) if m else ""
    m = re.search(
        r'<p[^>]*class="[^"]*entradilla[^"]*"[^>]*>(.*?)</p>',
        html_str, re.S | re.I,
    )
    entradilla = _text(m.group(1)) if m else ""
    body_parts = []
    after = html_str.find("</h1>")
    if after != -1:
        chunk = html_str[after:]
        stop = re.search(
            r"<(?:aside|footer|section[^>]*class=\"[^\"]*(?:comentarios|comments|footer|newsletter|whatsapp)[^\"]*\")",
            chunk, re.I,
        )
        if stop:
            chunk = chunk[:stop.start()]
        for pm in re.finditer(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I):
            txt = _text(pm.group(1))
            if len(txt) > 20:
                body_parts.append(txt)
    body = " ".join(body_parts)
    date_str = ""
    m = re.search(r'<div[^>]*class="[^"]*\bcuerpo\b[^"]*"[^>]*>(.*?)</div>', html_str, re.S | re.I)
    if m:
        date_str = _text(m.group(1))
    return {"h1": h1, "entradilla": entradilla, "body": body, "date_str": date_str}


def _parse_es_date(date_str):
    m = _RE_ES_DATE.search(date_str or "")
    if not m:
        return 0
    day = int(m.group(1))
    month = _ES_MONTHS.get(m.group(2).lower(), 0)
    year = int(m.group(3))
    hour = int(m.group(4) or 0)
    minute = int(m.group(5) or 0)
    if not month:
        return 0
    import datetime as _dt
    try:
        return int(_dt.datetime(year, month, day, hour, minute,
                                tzinfo=_dt.timezone.utc).timestamp())
    except Exception:
        return 0


def fetch_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def lookup_player_team(entradilla, h1):
    """If a known LaLiga team name appears in h1/entradilla, return its id.

    Strategy: for each known LaLiga team, build the set of (alias, weight)
    pairs — where weight is the alias length. Search the lowercased text
    once per alias. Longest alias wins, so 'Celta Vigo' (10) beats
    'Celta' (5) when both substrings match; but if only 'Celta' matches
    (e.g. 'previa del Celta'), we still resolve to that team.
    """
    try:
        import team_aliases as ta
    except Exception:
        return ""
    text_l = f"{h1} {entradilla}".lower()
    best_tid = ""
    best_len = 0
    for tid, entry in (ta.get_all() or {}).items():
        league = (entry or {}).get("league", "")
        if "LaLiga" not in league and "Spain > " not in league:
            continue
        name = (entry or {}).get("name", "")
        names_to_try = ([name] if name else []) + (entry.get("aliases") or [])
        # For each alias, also try individual words (>= 4 chars) as a
        # fallback substring match. Both the full alias and the word
        # variant are scored by length.
        cands = set()
        for alias in names_to_try:
            al = alias.lower().strip()
            if len(al) < 4:
                continue
            cands.add(al)
            for w in al.split():
                if len(w) >= 4:
                    cands.add(w)
        for al in cands:
            if re.search(r"(?<![a-záéíóúñ])" + re.escape(al) + r"(?![a-záéíóúñ])",
                         text_l) and len(al) > best_len:
                best_tid = tid
                best_len = len(al)
    return best_tid


def make_compare_url(team_id):
    if not team_id:
        return ("", "", "")
    data = fetch_json(f"{API_BASE}/lineup_ai/api/team/{team_id}/next_match")
    if not data or not data.get("match_found"):
        return ("", "", "")
    home_id = data.get("home_id", "")
    away_id = data.get("away_id", "")
    home_name = data.get("home_team", "")
    away_name = data.get("away_team", "")
    if not (home_id and away_id):
        return ("", "", "")
    qs = urllib.parse.urlencode({
        "mid": data.get("match_id", ""),
        "home_id": home_id,
        "away_id": away_id,
        "home_name": home_name,
        "away_name": away_name,
    })
    return (f"{SITE_BASE}/lineup_ai/compare/{team_id}?{qs}", home_name, away_name)


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


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def build_message(article):
    title = (article.get("h1") or article.get("title") or "").strip()
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rsplit(" ", 1)[0] + "..."
    body = article.get("body") or article.get("entradilla") or ""
    body = body.strip()
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY].rsplit(" ", 1)[0] + "..."

    parts = [f"⚠️ <b>{html_escape(title)}</b>"]
    if body:
        parts.append(html_escape(body))

    team_id = article.get("_team_id", "")
    if team_id:
        compare_url = article.get("_compare_url", "")
        home_name = article.get("_home_name", "")
        away_name = article.get("_away_name", "")
        if compare_url and home_name and away_name:
            link_text = f"{html_escape(home_name)} - {html_escape(away_name)}"
            parts.append(f'<a href="{html_escape(compare_url)}">{link_text}</a>')

    return "\n".join(parts)


def process_once(state):
    try:
        html_str = fetch(FEED_URL)
    except Exception as e:
        log(f"  fetch index failed: {e}")
        return 0

    items = parse_index(html_str)
    if not items:
        log("  index: 0 items parsed")
        return 0

    seen = set(state.get("seen") or [])
    sent = 0
    now = int(time.time())
    backfill_cutoff = now - BACKFILL_HOURS * 3600
    first_run = not seen

    for it in items[:30]:
        if it["id"] in seen:
            continue
        article = parse_article(fetch(it["url"]))
        date_ts = _parse_es_date(article["date_str"])
        if first_run and date_ts and date_ts < backfill_cutoff:
            log(f"  skip backfill (id={it['id']} ts={date_ts}): {article['h1'][:60]}")
            seen.add(it["id"])
            continue
        if first_run and not date_ts:
            log(f"  no date parsed for id={it['id']}: {article['date_str'][:80]!r}")

        merged = {**it, **article}
        team_id = lookup_player_team(article["entradilla"], article["h1"])
        if team_id:
            compare_url, home_name, away_name = make_compare_url(team_id)
            if compare_url:
                merged["_team_id"] = team_id
                merged["_compare_url"] = compare_url
                merged["_home_name"] = home_name
                merged["_away_name"] = away_name

        msg = build_message(merged)
        if send_telegram(msg):
            sent += 1
            seen.add(it["id"])
            log(f"  SENT: id={it['id']} {article['h1'][:60]!r}")
        else:
            log(f"  send failed for id={it['id']}, will retry next cycle")
            break

    state["seen"] = list(seen)[-500:]
    save_state(state)
    return sent


def main():
    log("=== news_notifier_ff starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    log(f"  STATE_PATH={STATE_PATH}  BACKFILL_HOURS={BACKFILL_HOURS}")
    state = load_state()
    log(f"  loaded state: {len(state.get('seen') or [])} seen ids")

    while True:
        try:
            n = process_once(state)
            if n:
                log(f"  cycle: sent {n} notification(s); "
                    f"state has {len(state.get('seen') or [])} ids")
        except Exception as e:
            log(f"  cycle error: {e!r}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)