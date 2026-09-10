"""
pxi_notifier.py — Sep 10 2026
Polls /lineup_ai/api/test_rotowire_matches/{league} for all 7 rotowire
leagues every 30s and sends Telegram notifications when Predicted XI
is published by rotowire (pxi_home_total > 0 or pxi_away_total > 0).

Mirrors sxi_notifier.py structure but:
  - Uses a different endpoint and triggers on pxi_*_total > 0
  - Sends 1-side or 2-side messages (1 ✅ / 2 ✅ ✅)
  - Match name is hyperlinked (parse_mode=HTML, spaces encoded as %20)

State file: /home/openclaw/FormAlert/data/pxi_state.json
Log file:   /home/openclaw/FormAlert/data/pxi_notifier.log
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# --- Config ---
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8099")
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44")
TG_CHAT = os.environ.get("TG_CHAT", "@lineupvalue_alert")
SITE_BASE = os.environ.get("SITE_BASE", "https://x11radar.ru")
DATA_DIR = Path("/home/openclaw/FormAlert/data")
STATE_PATH = DATA_DIR / "pxi_state.json"
LOG_PATH = DATA_DIR / "pxi_notifier.log"
INTERVAL = int(os.environ.get("PXI_INTERVAL", "30"))
PXI_MIN = int(os.environ.get("PXI_MIN", "1"))  # min players to count as published
# Only send if match starts within 18h (matches the endpoint's horizon)
HORIZON_SEC = 18 * 3600

LEAGUES = {
    "epl":  {"country": "England",  "league_name": "Premier League"},
    "liga": {"country": "Spain",    "league_name": "La Liga"},
    "seri": {"country": "Italy",    "league_name": "Serie A"},
    "bund": {"country": "Germany",  "league_name": "Bundesliga"},
    "fran": {"country": "France",   "league_name": "Ligue 1"},
    "ucl":  {"country": "Europe",   "league_name": "Champions League"},
    "mls":  {"country": "USA",      "league_name": "MLS"},
}


def log(msg: str) -> None:
    """Write a timestamped line to the log file (flush immediately)."""
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]   {msg}\n")
    except Exception as e:
        print(f"log error: {e}", file=sys.stderr)


def load_state() -> dict:
    """Load state from disk. Format: {match_id: {home_sent, away_sent, ...}}."""
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    """Atomic save: write to .tmp, then os.replace()."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        log(f"save_state error: {e}")


def fetch_matches(league_key: str) -> list:
    """Fetch matches from /lineup_ai/api/test_rotowire_matches/{league_key}."""
    url = f"{API_BASE}/lineup_ai/api/test_rotowire_matches/{league_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            return data.get("matches", [])
    except Exception as e:
        log(f"  [{league_key}] fetch error: {e}")
        return []


def make_url(home_id: str, away_id: str, home_name: str, away_name: str,
             league_key: str, kickoff_ts: int) -> str:
    """Build compare URL with %20 encoding (matches sxi_notifier format)."""
    params = {
        "mid": f"px-{home_id}-{away_id}",
        "home_id": home_id,
        "away_id": away_id,
        "home_name": home_name,
        "away_name": away_name,
        "rotowire_fran": "1",
        "rw_league": league_key,
        "kickoff_ts": kickoff_ts,
    }
    return (f"{SITE_BASE}/lineup_ai/compare/{home_id}?"
            + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))


def build_message(league_cfg: dict, match: dict, side: str) -> str:
    """Build Telegram message for P-XI notification.

    side: 'home' (1 ✅ left), 'away' (1 ✅ right), 'both' (✅ ... ✅)
    Match name is hyperlinked via HTML <a href>.
    """
    country = league_cfg["country"]
    league_name = league_cfg["league_name"]
    home_team = match.get("home_team", "?")
    away_team = match.get("away_team", "?")
    home_id = match.get("home_id") or "?"
    away_id = match.get("away_id") or "?"
    kickoff_ts = match.get("kickoff_ts", 0)
    lv_time = match.get("lv_time", "")
    if not lv_time and kickoff_ts:
        # CEST fallback (same logic as app.py)
        import datetime as _dt
        try:
            _cest = _dt.datetime.fromtimestamp(
                kickoff_ts, tz=_dt.datetime.now().astimezone().tzinfo)
            lv_time = _cest.strftime("%d.%m %H:%M")
        except Exception:
            lv_time = _dt.datetime.fromtimestamp(kickoff_ts).strftime("%d.%m %H:%M")
    if not lv_time:
        lv_time = "??.? ??"

    # Match S-XI format: wrap time in parens for visual separation
    # "10.09 21:00" -> "10.09 (21:00)" if it doesn't already have them.
    # "10.09 (21:00)" stays as-is.
    if lv_time and "(" not in lv_time:
        # Find the date/time boundary (last " " between date and time)
        idx = lv_time.rfind(" ")
        if idx > 0:
            lv_time = lv_time[:idx] + " (" + lv_time[idx+1:] + ")"
        else:
            lv_time = "(" + lv_time + ")"

    if side == "home":
        marker_left, marker_right = "✅", ""
    elif side == "away":
        marker_left, marker_right = "", "✅"
    else:  # both
        marker_left, marker_right = "✅", "✅"

    url = make_url(home_id, away_id, home_team, away_team,
                   match.get("_league_key", ""), kickoff_ts)
    # Hyperlink the match name (parse_mode=HTML); spaces around the link keep
    # the ✅ from rendering flush against the last letter of "Sabah FK".
    match_link = f'<a href="{url}">{home_team} - {away_team}</a>'

    return (
        f"🎯 Predicted XI\n"
        f"{country} - {league_name}\n"
        f"Date - {lv_time}\n"
        f"{marker_left} {match_link} {marker_right}"
    )


def send_telegram(message: str) -> bool:
    """Send a message via Telegram bot. Returns True on success."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TG_CHAT,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            if not data.get("ok"):
                log(f"  TG error: {data}")
                return False
            return True
    except Exception as e:
        log(f"  TG send error: {e}")
        return False


def match_key(league_key: str, home_id: str, away_id: str) -> str:
    """Stable match_id for state tracking."""
    return f"{league_key}-{home_id}-{away_id}"


def process_league(league_key: str, league_cfg: dict, state: dict,
                   now: int) -> int:
    """Process one league: check each match, send notifications for newly
    published sides. Returns the number of notifications sent."""
    matches = fetch_matches(league_key)
    sent = 0
    for m in matches:
        home_id = m.get("home_id") or ""
        away_id = m.get("away_id") or ""
        if not home_id and not away_id:
            continue
        # Skip matches outside the 18h horizon or already kicked off (>2h)
        kickoff_ts = m.get("kickoff_ts", 0) or 0
        if kickoff_ts and kickoff_ts < now - 2 * 3600:
            continue
        if kickoff_ts and kickoff_ts > now + HORIZON_SEC + 3600:
            continue

        ph_total = m.get("pxi_home_total", 0) or 0
        pa_total = m.get("pxi_away_total", 0) or 0
        ph_matched = m.get("pxi_home_matched", 0) or 0
        pa_matched = m.get("pxi_away_matched", 0) or 0

        # P-XI is "published" for a side when rotowire has at least N players listed
        pxi_home_published = ph_total >= PXI_MIN
        pxi_away_published = pa_total >= PXI_MIN

        if not (pxi_home_published or pxi_away_published):
            continue

        key = match_key(league_key, home_id or "?", away_id or "?")
        prev = state.get(key, {
            "home_sent": False, "away_sent": False,
            "home_team": m.get("home_team", ""),
            "away_team": m.get("away_team", ""),
        })

        # Decide which side(s) to send
        m["_league_key"] = league_key
        msg_side = None
        if pxi_home_published and pxi_away_published and not (prev["home_sent"] and prev["away_sent"]):
            msg_side = "both"
        elif pxi_home_published and not prev["home_sent"]:
            msg_side = "home"
        elif pxi_away_published and not prev["away_sent"]:
            msg_side = "away"

        if not msg_side:
            continue

        text = build_message(league_cfg, m, msg_side)
        if not send_telegram(text):
            continue

        # Update state
        if msg_side in ("home", "both"):
            prev["home_sent"] = True
        if msg_side in ("away", "both"):
            prev["away_sent"] = True
        prev["last_sent_at"] = now
        prev["last_sent_side"] = msg_side
        prev["home_team"] = m.get("home_team", "")
        prev["away_team"] = m.get("away_team", "")
        prev["kickoff_ts"] = kickoff_ts
        state[key] = prev
        sent += 1
        log(f"  [{league_key}] sent {msg_side} notification for "
            f"{m.get('home_team')} vs {m.get('away_team')} "
            f"(P-XI home={ph_matched}/{ph_total} away={pa_matched}/{pa_total})")
    return sent


def main() -> None:
    log("=== pxi_notifier starting ===")
    log(f"  API_BASE={API_BASE}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL}s")
    log(f"  STATE_PATH={STATE_PATH}  LEAGUES={list(LEAGUES)}  PXI_MIN={PXI_MIN}")
    state = load_state()
    log(f"  loaded state: {len(state)} match_ids")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    last_save = 0
    while True:
        cycle_start = int(time.time())
        now = cycle_start
        total_sent = 0
        try:
            for lk, cfg in LEAGUES.items():
                total_sent += process_league(lk, cfg, state, now)
        except Exception as e:
            log(f"cycle error: {e}")

        # Save state if we sent anything or every 60s
        if total_sent > 0 or (now - last_save) > 60:
            save_state(state)
            last_save = now

        log(f"  cycle: sent {total_sent} notification(s); "
            f"state has {len(state)} match_ids")

        # Sleep until next cycle
        elapsed = int(time.time()) - cycle_start
        sleep_for = max(5, INTERVAL - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
