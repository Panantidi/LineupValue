"""
news_notifier_ff.py — Sep 13 2026
Polls https://www.futbolfantasy.com/laliga/noticias every 60s and
forwards new player status articles to the LineupValue Telegram
channel @lineupvalue_alert.

We watch the article icon in the index:
  - icono_big_lesion.png       -> травма / medical report  (send)
  - icono_big_nodisponible.png -> недоступен / sanción     (send)
  - list.png                   -> вне заявки (выходы/возвраты) (send)
  - entreno.png                -> тренировка (статусы игроков) (send)
  - descanso.png               -> день отдыха (send)
  - everything else            -> not a status news (skip)

The article page is then fetched, h1 + entradilla + body are extracted
and sent to Telegram as one message per article. The first paragraph
of body that is pure boilerplate (e.g. "Jugadores lesionados de LaLiga",
"CEO y administrador de FutbolFantasy.com") is filtered out.

Format (per Max, Sep 13 2026):
  EMOJI <PlayerName>  — <StatusLabel>

  <H1>

  <Entradilla>

  <body paragraph 1>

  <body paragraph 2>
  ...
  <Read More (full URL)>

State: data/news_state.json — list of seen article URLs (no backfill
dump: on first run we DO send every status-article that's currently
on the index so the channel is fully populated).

Replaces the prior /ultimos-cambios poller (which only sent the
single-line event-row without the article body).

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
    "https://www.futbolfantasy.com/laliga/noticias",
)
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_INTERVAL_SEC", "60"))
MAX_BODY_PARAS = int(os.environ.get("NEWS_MAX_BODY_PARAS", "4"))
MAX_BODY_CHARS = int(os.environ.get("NEWS_MAX_BODY_CHARS", "700"))

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_ff.log"

# Icons we forward
STATUS_ICONS = {
    "icono_big_lesion",
    "icono_big_nodisponible",
    "list",
    "entreno",
    "descanso",
}

# Status keywords (Spanish) → (emoji, English label)
STATUS_KEYWORDS = [
    (re.compile(r"\bbaja\b|\blesionad[oa]\b|\blesión\b|\brotura\b|\brotura fibrilar\b", re.I), "🔴", "Injured"),
    (re.compile(r"\btocad[oa]\b|\bmolestias\b|\baductor\b|\bpruebas m[eé]dicas\b", re.I), "🟡", "Tocado"),
    (re.compile(r"\bduda\b|\bdudas\b", re.I), "🟠", "Doubt"),
    (re.compile(r"\bsancionad[oa]\b|\bexpulsad[oa]\b|\bsanci[oó]n\b", re.I), "🔴", "Suspended"),
    (re.compile(r"\brecuperad[oa]\b|\balta (?:m[eé]dica|hospitalaria)\b|\bvuelve\b|\bviaja\b", re.I), "🟢", "Available"),
    (re.compile(r"\bdisponible\b", re.I), "🟢", "Available"),
]

# Boilerplate paragraphs to strip from body (author bios, link lists)
BOILERPLATE_PARAS = (
    "Jugadores lesionados",
    "Jugadores sancionados",
    "Jugadores apercibidos",
    "Jugadores en duda",
    "Jugadores tocados",
    "CEO y administrador",
    "Programador informático",
    "Redactor jefe",
    "CEO y redactor",
    "Redactor y community",
    "Analista fantasy",
    "CEO de FutbolFantasy",
    "Fundador de FutbolFantasy",
    "Si te ha gustado",
    "Apuesta en tu casa",
    "Publicación autorizada",
    "Apuestas de fútbol",
)

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_RE_INDEX_ARTICLE = re.compile(
    r'<div class="date">([^<]+)</div>\s*'
    r'<img class="icon" src="[^"]*/tiponoticia/([a-z_]+)\.png"[^>]*/?>'
    r'\s*<a class="link" href="(https?://[^"]+)">([^<]+)</a>',
    re.S,
)
_RE_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_RE_ENTRADILLA = re.compile(
    r'<p[^>]*class="[^"]*entradilla[^"]*"[^>]*>(.*?)</p>', re.S | re.I
)
_RE_PARA = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)


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


def text_only(html_str):
    if not html_str:
        return ""
    s = _HTML_TAG.sub(" ", html_str)
    s = unescape(s)
    s = _WS.sub(" ", s).strip()
    return s


def detect_status(h1, entradilla):
    """Walk STATUS_KEYWORDS over h1+entradilla, return (emoji, label) or None."""
    blob = f"{h1}  {entradilla}"
    for pat, emoji, label in STATUS_KEYWORDS:
        if pat.search(blob):
            return emoji, label
    return None


def extract_player_name(h1):
    """Heuristic: title is 'Name ... status word ...' — first word(s) before
    the first verb-ish token is the player name. E.g.:
      'Aspas termina el partido del Málaga tocado del aductor' -> 'Aspas'
      'Aitor Mañas recibe el alta hospitalaria'                -> 'Aitor Mañas'
      'Dotor, baja de última hora por un virus'                -> 'Dotor'
    """
    s = h1.strip()
    # Strip leading "Sanción para X", "Lesión de X", "Baja de X" prefixes
    s = re.sub(
        r"^(?:sanción para|lesión de|baja de|parte m[eé]dico de|el(?:/la)?)\s+",
        "", s, flags=re.I,
    ).strip(" ,.")
    # Take everything up to the first verb-ish word
    m = re.match(
        r"^([A-ZÁÉÍÓÚÑ][\w\.\-]+(?:\s+[A-ZÁÉÍÓÚÑ][\w\.\-]+)?)", s)
    if m:
        return m.group(1).strip()
    return s.split(" ", 1)[0] if s else ""


def parse_index(html_str):
    """Yield dicts: {date, icon, url, title} for every article on /laliga/noticias."""
    for m in _RE_INDEX_ARTICLE.finditer(html_str):
        d, icon, url, title = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
        yield {"date": d, "icon": icon, "url": url, "title": text_only(title)}


def parse_article(html_str):
    """Return {h1, entradilla, body_paras} where body_paras is a list[str]."""
    m = _RE_H1.search(html_str)
    h1 = text_only(m.group(1)) if m else ""
    m = _RE_ENTRADILLA.search(html_str)
    entradilla = text_only(m.group(1)) if m else ""
    paras = []
    after = html_str.find("</h1>")
    if after != -1:
        chunk = html_str[after:]
        stop = re.search(
            r"<(?:aside|footer|section[^>]*class=\"[^\"]*(?:comentarios|comments|footer|newsletter|whatsapp|compartir|newsletter)[^\"]*\")",
            chunk, re.I,
        )
        if stop:
            chunk = chunk[:stop.start()]
        for pm in _RE_PARA.finditer(chunk):
            t = text_only(pm.group(1))
            if len(t) <= 20:
                continue
            if any(t.startswith(b) for b in BOILERPLATE_PARAS):
                continue
            # Avoid duplicating the entradilla
            if t == entradilla:
                continue
            paras.append(t)
    return {"h1": h1, "entradilla": entradilla, "body_paras": paras}


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def build_message(h1, entradilla, body_paras, player, status_emoji, status_label, url):
    # Header: <emoji> <Player>  — <StatusLabel>
    header = f"{status_emoji} {html_escape(player)}  — {status_label}"
    parts = [header, "", html_escape(h1)]
    if entradilla:
        parts.append("")
        parts.append(html_escape(entradilla))
    # Body
    if body_paras:
        parts.append("")
        for p in body_paras[:MAX_BODY_PARAS]:
            parts.append(html_escape(p))
    # Read More link
    parts.append("")
    parts.append(f'<a href="{html_escape(url)}">Read More ({html_escape(url)})</a>')
    text = "\n".join(parts)
    # Telegram hard cap is 4096; trim body if needed
    if len(text) > 4000:
        # drop trailing body paragraphs until it fits
        while len(text) > 3800 and body_paras:
            body_paras.pop()
            parts = [header, "", html_escape(h1)]
            if entradilla:
                parts.append("")
                parts.append(html_escape(entradilla))
            if body_paras:
                parts.append("")
                for p in body_paras[:MAX_BODY_PARAS]:
                    parts.append(html_escape(p))
            parts.append("")
            parts.append(f'<a href="{html_escape(url)}">Read More ({html_escape(url)})</a>')
            text = "\n".join(parts)
    return text


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
    accepted = 0
    skipped_dup = 0
    skipped_no_status = 0
    skipped_icon = 0

    # On the first run we DO send the current status articles (full
    # backfill, so the channel is populated). After that, only new ones.
    # We don't suppress the dump because the channel is empty otherwise.
    is_first_run = not seen

    for item in parse_index(html_str):
        if item["icon"] not in STATUS_ICONS:
            skipped_icon += 1
            continue
        accepted += 1
        if item["url"] in seen:
            skipped_dup += 1
            continue

        try:
            art_html = fetch(item["url"])
        except Exception as e:
            log(f"  fetch article failed for {item['url']}: {e}")
            continue
        art = parse_article(art_html)
        status = detect_status(art["h1"], art["entradilla"])
        if not status:
            skipped_no_status += 1
            seen.add(item["url"])
            continue
        emoji, label = status
        player = extract_player_name(art["h1"])
        msg = build_message(
            art["h1"], art["entradilla"], art["body_paras"],
            player, emoji, label, item["url"],
        )
        if send_telegram(msg):
            sent += 1
            seen.add(item["url"])
            log(f"  SENT: {art['h1'][:80]!r}  status={emoji}{label}")
        else:
            log(f"  send failed for {item['url']}, will retry")
            break

    state["seen"] = list(seen)[-2000:]
    save_state(state)
    log(
        f"  cycle: skipped_icon={skipped_icon}  accepted={accepted}  "
        f"skipped_dup={skipped_dup}  skipped_no_status={skipped_no_status}  "
        f"sent={sent}  state_size={len(seen)}"
    )
    return sent


def main():
    log("=== news_notifier_ff (article feed) starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    state = load_state()
    log(f"  loaded state: {len(state.get('seen') or [])} seen urls")

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
