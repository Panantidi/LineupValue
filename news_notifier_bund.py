"""
news_notifier_bund.py — Sep 13 2026
Polls https://www.ligainsider.de/bundesliga/verletzte-und-gesperrte-spieler/
every 60s and forwards new injury / suspension / doubt entries to the
LineupValue Telegram channel @lineupvalue_alert.

The page lists absent players per Bundesliga club. Each row has an
icon that encodes the status:
  verletzung         -> 🔴 Injured
  angeschlagen-down  -> 🟠 Doubt
  aufbautraining     -> 🟢 Recovery
  gelb-rote-karte    -> 🔴 Suspended
  verbannung         -> skipped (Nicht im Kader — coach decision, not news)

A "new" entry is one of:
  (a) a player that was NOT in the previous snapshot;
  (b) a player whose status icon / Grund changed (e.g. doubt -> injury).

When a row's icon is the same as before we treat it as unchanged and
do not send anything.

We group by TEAM — one Telegram message per team that has any changes,
listing every changed player in the same format as the LaLiga and
EPL feeds:

  🔴 Emre Can — Injured
  🟠 Sebastiaan Bornauw — Doubt

  "Kreuzbandriss"          (Grund / last news title if available)

  Source: https://www.ligainsider.de/...
  #Germany

State: data/news_state_bund.json — {player_href: last_icon|grund|grund_label}

Run: python3 news_notifier_bund.py
Restart: bash /home/openclaw/FormAlert/start_news_notifier_bund.sh
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
    "NEWS_BUND_FEED_URL",
    "https://www.ligainsider.de/bundesliga/verletzte-und-gesperrte-spieler/",
)
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_BUND_INTERVAL_SEC", "60"))
HASHTAG = "#Germany"
BASE_URL = "https://www.ligainsider.de"

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state_bund.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_bund.log"

# Status icon → (emoji, English label)
ICON_MAP = {
    "verletzung": ("🔴", "Injured"),
    "angeschlagen-down": ("🟠", "Doubt"),
    "aufbautraining": ("🟢", "Recovery"),
    "gelb-rote-karte": ("🔴", "Suspended"),
}

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_RE_H2 = re.compile(r'<h2 class="text-uppercase float-start">([^<]+)</h2>')
_RE_PLAYER_HREF = re.compile(r'<a href="/([a-z0-9_-]+)/"><div class="left_title"><strong>([^<]+)</strong>')
_RE_ICON = re.compile(r'images/icons/new/icon/([a-z0-9_-]+)\.png"')
_RE_GRUND = re.compile(r'small_table_column2 float-start"><span>([^<]*)</span>', re.S)
_RE_NEWS = re.compile(
    r'small_table_column3 float-start"><span><a href="([^"]+)">([^<]+)</a>',
    re.S,
)
_RE_SINCE = re.compile(r'small_table_column4 float-end"><span>([^<]+)</span>', re.S)


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
        return {"by_player": {}}
    try:
        return json.loads(STATE_PATH.read_text("utf-8") or "{}")
    except Exception:
        return {"by_player": {}}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def fetch(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
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


def parse(html_str):
    """Yield per-team dicts:
        {"team": "Borussia Dortmund", "rows": [
            {"href": "/emre-can_1812", "name": "Emre Can", "icon": "verletzung",
             "grund": "Kreuzbandriss", "news_title": "...", "news_url": "...",
             "since": "6 Monaten und 2 Wochen"},
            ...
        ]}
    """
    # Split by personal_table; each section starts with h2 (team name)
    parts = re.split(r'<div class="personal_table[^"]*">', html_str)
    for part in parts[1:]:
        h2_m = _RE_H2.search(part)
        if not h2_m:
            continue
        team = text_only(h2_m.group(1))
        rows = []
        for row_block in part.split('<div class="small_table_row">')[1:]:
            href_m = _RE_PLAYER_HREF.search(row_block)
            icon_m = _RE_ICON.search(row_block)
            if not href_m or not icon_m:
                continue
            href = "/" + href_m.group(1)
            name = text_only(href_m.group(2))
            icon = icon_m.group(1)
            if icon not in ICON_MAP:
                continue
            grund_m = _RE_GRUND.search(row_block)
            grund = text_only(grund_m.group(1)) if grund_m else ""
            news_m = _RE_NEWS.search(row_block)
            news_url = news_m.group(1) if news_m else ""
            news_title = text_only(news_m.group(2)) if news_m else ""
            since_m = _RE_SINCE.search(row_block)
            since = text_only(since_m.group(1)) if since_m else ""
            rows.append({
                "href": href,
                "name": name,
                "icon": icon,
                "grund": grund,
                "news_url": news_url,
                "news_title": news_title,
                "since": since,
            })
        if rows:
            yield {"team": team, "rows": rows}


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def build_team_message(team, changed_rows):
    """changed_rows: list of {name, icon, grund, news_title, news_url, since}.
    Returns Telegram HTML text.
    """
    # Header lines
    header_lines = []
    seen_lines = set()
    body_lines = []
    for r in changed_rows:
        emoji, label = ICON_MAP[r["icon"]]
        line = f"{emoji} {r['name']} — {label}"
        if line not in seen_lines:
            header_lines.append(line)
            seen_lines.add(line)
        # Pick the most informative body note
        note = r["news_title"] or r["grund"]
        if note and note not in body_lines:
            body_lines.append(note)

    parts = list(header_lines)
    if body_lines:
        parts.append("")
        parts.extend(html_escape(b) for b in body_lines)
    parts.append("")
    parts.append(f"Source: {html_escape(FEED_URL)}")
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

    by_player = state.get("by_player") or {}
    is_first_run = not by_player

    # Collect per-team new/changed rows
    team_changes = []
    seen_now = {}
    for team_data in parse(html_str):
        team_changes_for_team = []
        for row in team_data["rows"]:
            fp = f"{row['href']}|{row['icon']}|{row['grund']}"
            seen_now[row["href"]] = {
                "icon": row["icon"],
                "grund": row["grund"],
                "name": row["name"],
            }
            if is_first_run:
                continue
            prev = by_player.get(row["href"])
            if prev is None:
                # new player in the injury list
                team_changes_for_team.append(("new", row))
            elif prev.get("icon") != row["icon"] or prev.get("grund") != row["grund"]:
                # status changed (e.g. doubt -> injury)
                team_changes_for_team.append(("changed", row, prev))
        if team_changes_for_team:
            team_changes.append((team_data["team"], team_changes_for_team))

    if is_first_run:
        state["by_player"] = seen_now
        save_state(state)
        log(f"  first run: seeded {len(seen_now)} players; no notifications sent")
        return 0

    sent = 0
    for team, changes in team_changes:
        # Build a single message for the team listing every changed player
        rows_for_msg = [c[1] if len(c) == 2 else c[1] for c in changes]
        msg = build_team_message(team, rows_for_msg)
        if send_telegram(msg):
            sent += 1
            summary = ", ".join(
                f"{r['name']}({r['icon']})" for r in rows_for_msg
            )
            log(f"  SENT team={team!r}  {summary}")
        else:
            log(f"  send failed for team={team!r}, will retry")
            break

    state["by_player"] = seen_now
    save_state(state)
    log(f"  cycle: players_now={len(seen_now)} teams_with_changes={len(team_changes)} sent={sent}")
    return sent


def main():
    log("=== news_notifier_bund (ligainsider Bundesliga) starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    state = load_state()
    log(f"  loaded state: {len(state.get('by_player') or {})} known players")

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
