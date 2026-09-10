"""
sxi_notifier.py — Sep 10 2026
Polls /lineup_ai/api/starting_xi_matches/{league} for all 7 rotowire
leagues every 30s and sends Telegram notifications when a team's
starting XI is confirmed (sxi_home_confirmed / sxi_away_confirmed).

State per match_id:
  home_sent: bool  — telegram sent for home confirmed
  away_sent: bool  — telegram sent for away confirmed
  kickoff_ts: int  — for staleness check (skip matches >2h after kickoff)

Template (single line, with checkmarks as the user wants):
  🏁 Starting XI
  <Country> - <League>
  Date - <DD.MM> (<HH:MM>)
  ✅ <Home> - <Away> (<url>)         # one side confirmed
  ✅ <Home> - <Away> (<url>) ✅      # both confirmed

Run: python3 sxi_notifier.py
Config: env vars SXI_TG_TOKEN, SXI_TG_CHAT, SXI_INTERVAL_SEC (default 30)
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import threading
from datetime import datetime
from pathlib import Path

API_BASE = os.environ.get("SXI_API_BASE", "http://127.0.0.1:8099")
TG_TOKEN = os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44")
TG_CHAT = os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
INTERVAL = int(os.environ.get("SXI_INTERVAL_SEC", "30"))
SITE_BASE = os.environ.get("SXI_SITE_BASE", "https://x11radar.ru")
STATE_PATH = Path(os.environ.get(
    "SXI_STATE_PATH",
    "/home/openclaw/FormAlert/data/sxi_state.json",
))
LOG_PATH = Path(os.environ.get(
    "SXI_LOG_PATH",
    "/home/openclaw/FormAlert/data/sxi_notifier.log",
))

LEAGUES = {
    "epl":  {"country": "England", "league": "Premier League"},
    "liga": {"country": "Spain",   "league": "LaLiga"},
    "seri": {"country": "Italy",   "league": "Serie A"},
    "bund": {"country": "Germany", "league": "Bundesliga"},
    "fran": {"country": "France",  "league": "Ligue 1"},
    "ucl":  {"country": "Europe",  "league": "Champions League"},
    "mls":  {"country": "USA",     "league": "MLS"},
}

_state_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"WARN: state load failed: {e}; starting empty")
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def fetch_matches(league_key: str) -> list:
    """Hit the local /lineup_ai/api/starting_xi_matches/{league_key} endpoint."""
    url = f"{API_BASE}/lineup_ai/api/starting_xi_matches/{league_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("matches", [])
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        log(f"  [{league_key}] fetch error: {e}")
        return []


def send_telegram(text: str) -> bool:
    """Post text to Telegram via sendMessage. Returns True on success."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TG_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return True
            log(f"  tg send FAILED: {body}")
            return False
    except Exception as e:
        log(f"  tg send EXC: {e}")
        return False


def make_url(home_id: str, away_id: str, home_team: str, away_team: str,
             league_key: str, kickoff_ts: int) -> str:
    """Build the deep-link URL into the LineupValue compare page."""
    mid = f"sx-{home_id}-{away_id}"
    params = {
        "mid": mid,
        "home_id": home_id,
        "away_id": away_id,
        "home_name": home_team,
        "away_name": away_team,
        "rotowire_fran": "1",
        "rw_league": league_key,
        "kickoff_ts": str(kickoff_ts or 0),
    }
    # quote_via=quote produces %20 (matches the format in the user's spec);
    # the default would use + for spaces (also valid in query strings).
    return (f"{SITE_BASE}/lineup_ai/compare/{home_id}?"
            + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))


def build_message(league_cfg: dict, m: dict, side: str) -> str:
    """Build the telegram message text.

    side: 'home' (only home confirmed), 'away' (only away confirmed), 'both'.
    """
    home_team = m.get("home_team", "?")
    away_team = m.get("away_team", "?")
    home_id = m.get("home_id", "")
    away_id = m.get("away_id", "")
    league_key = m.get("_league_key", "ucl")
    kickoff_ts = m.get("kickoff_ts", 0)
    lv_time = m.get("lv_time") or ""

    url = make_url(home_id, away_id, home_team, away_team, league_key, kickoff_ts)

    if not lv_time and kickoff_ts:
        try:
            from datetime import datetime as _dt
            lv_time = _dt.fromtimestamp(kickoff_ts).strftime("%d.%m (%H:%M)")
        except Exception:
            lv_time = "?"
    if not lv_time:
        lv_time = "?"
    # lv_time currently "DD.MM HH:MM" — convert to "DD.MM (HH:MM)"
    lv_time = lv_time.strip()
    if lv_time and "(" not in lv_time and " " in lv_time:
        d, t = lv_time.split(" ", 1)
        lv_time = f"{d} ({t})"

    country = league_cfg.get("country", "?")
    league_name = league_cfg.get("league", "?")

    if side == "home":
        marker_left = "✅"
        marker_right = ""
    elif side == "away":
        marker_left = ""
        marker_right = "✅"
    else:  # both
        marker_left = "✅"
        marker_right = "✅"

    return (
        f"🏁 Starting XI\n"
        f"{country} - {league_name}\n"
        f"Date - {lv_time}\n"
        f"{marker_left} {home_team} - {away_team} ({url}){marker_right}"
    )


def process_league(league_key: str, league_cfg: dict, state: dict) -> int:
    """Process one league: check each match, send notifications for newly
    confirmed sides. Returns the number of notifications sent.

    State semantics:
      - First run (empty state): all currently-confirmed matches get a
        notification. This is the expected "backfill" — the user wants
        to see all currently-confirmed lineups as soon as the bot is
        added to the channel.
      - Subsequent runs: only newly-confirmed sides trigger a notification.
        A match that flips home→home+away sends a second message with
        two ✅ markers.
    """
    matches = fetch_matches(league_key)
    sent = 0
    now = int(time.time())
    for m in matches:
        home_id = m.get("home_id", "")
        away_id = m.get("away_id", "")
        if not home_id or not away_id:
            continue
        sxi_home = bool(m.get("sxi_home_confirmed"))
        sxi_away = bool(m.get("sxi_away_confirmed"))
        if not sxi_home and not sxi_away:
            continue
        # match_id: stable across runs (rotowire gives both ids)
        match_id = f"{league_key}-{home_id}-{away_id}"
        # Skip matches that started >2h ago (no point notifying late)
        kickoff_ts = m.get("kickoff_ts", 0) or 0
        if kickoff_ts and kickoff_ts < now - 2 * 3600:
            continue
        prev = state.get(match_id, {})
        prev_home = bool(prev.get("home_sent"))
        prev_away = bool(prev.get("away_sent"))
        m["_league_key"] = league_key
        # Determine if anything new to send
        if sxi_home and not prev_home:
            # send single-side (home) or both-side notification
            side = "both" if sxi_away else "home"
            text = build_message(league_cfg, m, side)
            ok = send_telegram(text)
            if ok:
                state[match_id] = {
                    "home_sent": True,
                    "away_sent": sxi_away,  # if both, mark both
                    "home_team": m.get("home_team"),
                    "away_team": m.get("away_team"),
                    "kickoff_ts": kickoff_ts,
                    "last_sent_at": now,
                    "last_sent_side": side,
                }
                sent += 1
                log(f"  [{league_key}] sent {side} notification for "
                    f"{m.get('home_team')} vs {m.get('away_team')}")
        elif sxi_away and not prev_away and prev_home:
            # home was sent earlier; now away is confirmed too
            text = build_message(league_cfg, m, "both")
            ok = send_telegram(text)
            if ok:
                state[match_id]["away_sent"] = True
                state[match_id]["last_sent_at"] = now
                state[match_id]["last_sent_side"] = "both"
                sent += 1
                log(f"  [{league_key}] sent BOTH notification for "
                    f"{m.get('home_team')} vs {m.get('away_team')}")
        # also: if both confirmed at once and prev says nothing, we already
        # sent it via the sxi_home branch above
    return sent


def main():
    log(f"=== sxi_notifier starting ===")
    log(f"  API_BASE={API_BASE}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL}s")
    log(f"  STATE_PATH={STATE_PATH}  LEAGUES={list(LEAGUES.keys())}")
    state = load_state()
    log(f"  loaded state: {len(state)} match_ids")
    last_save = time.time()
    while True:
        try:
            with _state_lock:
                total_sent = 0
                for league_key, league_cfg in LEAGUES.items():
                    total_sent += process_league(league_key, league_cfg, state)
                if total_sent > 0 or time.time() - last_save > 60:
                    save_state(state)
                    last_save = time.time()
                if total_sent:
                    log(f"  cycle: sent {total_sent} notification(s); "
                        f"state has {len(state)} match_ids")
        except KeyboardInterrupt:
            log("=== interrupted; saving state and exiting ===")
            with _state_lock:
                save_state(state)
            return
        except Exception as e:
            log(f"ERROR in main loop: {e}")
            import traceback
            log(traceback.format_exc())
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
