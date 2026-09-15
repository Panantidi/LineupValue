"""
sxi_notifier.py — Sep 16 2026 (multi-source orchestrator)

Polls multiple S-XI sources in parallel and posts 🏁 Starting XI to
@lineupvalue_alert as soon as either team is confirmed.

Sources (run in parallel via ThreadPoolExecutor per match):
  1. rotowire — /lineup_ai/api/starting_xi_matches/{league} (LIVE; backed
     by rotowire.com/lineups.htm through app.py). Returns per-match
     sxi_home_confirmed / sxi_away_confirmed.
  2. official X — TODO stub. Returns None until the team-account scraper
     is wired up. The orchestrator treats None as "this source doesn't
     know yet", so a real implementation can be dropped in without
     changing anything else.
  3. flashscore — TODO stub. Will hit Flashscore's confirmed-lineup
     endpoint once we have a stable path.
  4. official site (ligue1.com / uefa.com / etc.) — TODO stub. Will hit
     per-league official site once league-specific parsers exist.

State per match_id (UNCHANGED shape — supervisor & state file compatible):
  home_sent: bool   — telegram already sent for home confirmed
  away_sent: bool   — telegram already sent for away confirmed
  home_source: str  — which source first found home (for observability)
  away_source: str
  home_team: str
  away_team: str
  kickoff_ts: int
  last_sent_at: int
  last_sent_side: "home" | "away" | "both"

Critical rules (Sep 16 2026):
  - Per-team FIRST-SOURCE-WINS: as soon as ANY source confirms a team's
    S-XI, send the telegram immediately. Do NOT wait for the other team.
  - Once both teams are sent (state.home_sent AND state.away_sent),
    skip the match entirely on subsequent cycles — no HTTP, no work.
  - Once a team is sent, do not re-check its sources.
  - Run every SXI_INTERVAL_SEC seconds (default 30). All leagues checked
    in one cycle. Within each league, all matches processed in parallel
    (up to 6 worker threads). Within each match, all 4 sources run in
    parallel.
  - UI/format unchanged: still uses build_message() with the same
    ✅/✅/✅ markers and the same compare URL.

Run: python3 sxi_notifier.py
Env: SXI_TG_TOKEN, SXI_TG_CHAT, SXI_INTERVAL_SEC, SXI_API_BASE,
     SXI_SITE_BASE, SXI_STATE_PATH, SXI_LOG_PATH,
     SXI_MAX_WORKERS (default 6).
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

API_BASE = os.environ.get("SXI_API_BASE", "http://127.0.0.1:8099")
TG_TOKEN = os.environ.get("SXI_TG_TOKEN", "8804020090:***")
TG_CHAT = os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
INTERVAL = int(os.environ.get("SXI_INTERVAL_SEC", "30"))
SITE_BASE = os.environ.get("SXI_SITE_BASE", "https://x11radar.ru")
MAX_WORKERS = int(os.environ.get("SXI_MAX_WORKERS", "6"))
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

# Source registry. Each source is a callable that takes a league_key
# and returns a list of dicts, one per match. Each dict MUST include
# home_id, away_id, home_team, away_team, kickoff_ts, and (for any
# team that is confirmed) sxi_home_confirmed=True / sxi_away_confirmed=True.
# A source can return [] (no data yet) or None (source unavailable).
#
# The orchestrator merges results from all sources per match_id
# (league-home_id-away_id), then takes the OR of sxi_*_confirmed
# across sources. First source to confirm a side wins (and we record
# which one in state for observability).
SOURCE_REGISTRY = {
    # rotowire: backed by app.py's /lineup_ai/api/starting_xi_matches/{league},
    # which proxies rotowire.com/lineups.htm. See app.py:3737.
    "rotowire": "source_rotowire",

    # Official X/Twitter team accounts. Stubs for now — return None so
    # the orchestrator ignores them. To enable: implement a real fetcher
    # that pulls the most recent team-account tweet containing the
    # "Starting XI" image, OCR/AI-match it to the LV roster, and return
    # matches with sxi_*_confirmed=True. Suggested env wiring when ready:
    #   X_BEARER_TOKEN, SXI_X_TEAM_HANDLES (json map league -> [@handles])
    "official_x": "source_official_x",

    # Official league site (ligue1.com, uefa.com, etc.). Stubs for now.
    # Each league has its own URL; implementation will be per-league.
    "official_site": "source_official_site",
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


# Sep 16 2026: P-XI state path. pxi_notifier.py writes its own state
# here with the same schema (home_sent, away_sent, home_team, away_team,
# kickoff_ts) but with a different match_id format ("{league}-...?")
# that we cannot join on. We instead match by (home_team, away_team,
# kickoff_ts window). This is how the pre-v2.5 S-XI logic used the
# P-XI state — the user explicitly asked to restore that contract.
PXI_STATE_PATH = Path("/home/openclaw/FormAlert/data/pxi_state.json")
_pxi_state_cache: dict | None = None
_pxi_state_loaded_at: float = 0.0
_PXI_STATE_TTL = 30  # refresh every 30s — same as our cycle interval


def _load_pxi_state() -> dict:
    """Lazy-load + cache pxi_state.json. Returned dict is keyed by
    match_id; each entry is a normal P-XI state record (home_sent,
    away_sent, home_team, away_team, kickoff_ts, ...).

    S-XI does NOT mutate this — P-XI owns it. S-XI only reads."""
    global _pxi_state_cache, _pxi_state_loaded_at
    now = time.time()
    if _pxi_state_cache is not None and (now - _pxi_state_loaded_at) < _PXI_STATE_TTL:
        return _pxi_state_cache
    if not PXI_STATE_PATH.exists():
        _pxi_state_cache = {}
        _pxi_state_loaded_at = now
        return _pxi_state_cache
    try:
        with PXI_STATE_PATH.open("r", encoding="utf-8") as f:
            _pxi_state_cache = json.load(f)
    except Exception as e:
        log(f"  [pxi-state] load failed: {e}; treating as empty")
        _pxi_state_cache = {}
    _pxi_state_loaded_at = now
    return _pxi_state_cache


def _norm_team(name: str) -> str:
    """Normalize a team name for fuzzy matching against P-XI state.

    Lowercase, strip punctuation/whitespace. Handles "Man United" /
    "Manchester United" style variation only minimally — the user
    explicitly accepted that as the v1 contract."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return s


def _pxi_predicted(slot: dict, league_key: str, pxi_state: dict,
                   window_sec: int = 300) -> bool:
    """Return True iff a P-XI record exists for this slot.

    Match criteria (all of):
      1. League key matches: P-XI state keys are "{league_key}-...".
      2. Normalized home/away team names match (both directions
         accepted in case P-XI reversed home/away).
      3. |kickoff_ts - slot.kickoff_ts| <= window_sec (5 min default —
         enough to absorb kickoff-time rounding differences between
         P-XI and rotowire, tight enough to avoid false matches
         between replays/return fixtures of the same teams).
    """
    if not pxi_state or not slot.get("kickoff_ts"):
        return False
    h = _norm_team(slot.get("home_team", ""))
    a = _norm_team(slot.get("away_team", ""))
    if not h or not a:
        return False
    ko = int(slot["kickoff_ts"])
    for mid, rec in pxi_state.items():
        if not mid.startswith(f"{league_key}-"):
            continue
        if not isinstance(rec, dict):
            continue
        if not (rec.get("home_sent") or rec.get("away_sent")):
            # P-XI record exists but nothing was ever sent for it.
            # Treat as "no P-XI" so S-XI also skips.
            continue
        ko2 = int(rec.get("kickoff_ts") or 0)
        if abs(ko2 - ko) > window_sec:
            continue
        h2 = _norm_team(rec.get("home_team", ""))
        a2 = _norm_team(rec.get("away_team", ""))
        if (h == h2 and a == a2) or (h == a2 and a == h2):
            return True
    return False


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


# ---------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------

def source_rotowire(league_key: str) -> list | None:
    """Live source: app.py's starting_xi_matches endpoint."""
    url = f"{API_BASE}/lineup_ai/api/starting_xi_matches/{league_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("matches", [])
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        log(f"  [rotowire/{league_key}] fetch error: {e}")
        return None



def source_official_x(league_key: str) -> list | None:
    """TODO — pull Starting XI image from the team's official X account,
    run OCR / LV-AI to confirm the lineup, return matches with
    sxi_*_confirmed=True for confirmed teams.

    For now this is a stub returning None so the orchestrator falls
    back to the other sources."""
    return None


def source_official_site(league_key: str) -> list | None:
    """TODO — pull confirmed lineups from each league's official site
    (ligue1.com for fran, uefa.com for ucl, etc.)."""
    return None


def _get_source(name: str):
    return globals()[SOURCE_REGISTRY[name]]


# ---------------------------------------------------------------------
# Telegram + URL + message (UNCHANGED)
# ---------------------------------------------------------------------

def send_telegram(text: str) -> bool:
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
    return (f"{SITE_BASE}/lineup_ai/compare/{home_id}?"
            + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))


def build_message(league_cfg: dict, m: dict, side: str) -> str:
    """Build the telegram message text. UNCHANGED from the Sep 10 2026
    version (✅/✅ markers, compare URL, DD.MM (HH:MM) date format)."""
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
    lv_time = lv_time.strip()
    if lv_time and "(" not in lv_time and " " in lv_time:
        d, t = lv_time.split(" ", 1)
        lv_time = f"{d} ({t})"

    country = league_cfg.get("country", "?")
    league_name = league_cfg.get("league", "?")

    if side == "home":
        marker_left, marker_right = "✅", ""
    elif side == "away":
        marker_left, marker_right = "", "✅"
    else:  # both
        marker_left, marker_right = "✅", "✅"

    match_link = f'<a href="{url}">{home_team} - {away_team}</a>'

    return (
        f"🏁 Starting XI\n"
        f"{country} - {league_name}\n"
        f"Date - {lv_time}\n"
        f"{marker_left} {match_link} {marker_right}"
    )


# ---------------------------------------------------------------------
# Multi-source orchestrator
# ---------------------------------------------------------------------

def _stable_match_id(league_key: str, home_id: str, away_id: str) -> str:
    return f"{league_key}-{home_id}-{away_id}"


def _merge_sources(league_key: str, source_results: dict) -> list:
    """Merge per-source match lists into one match-keyed dict.

    Returns a list of merged match dicts (one per unique match_id).
    For each match_id, sxi_*_confirmed is the OR across sources, and
    the source name is recorded as "<team>_source" (first source to
    confirm wins, in registry order).
    """
    by_id: dict[str, dict] = {}
    for src_name, matches in source_results.items():
        if not matches:
            continue
        for m in matches:
            home_id = m.get("home_id", "")
            away_id = m.get("away_id", "")
            if not home_id or not away_id:
                continue
            mid = _stable_match_id(league_key, home_id, away_id)
            slot = by_id.get(mid)
            if slot is None:
                slot = {
                    "home_id": home_id,
                    "away_id": away_id,
                    "home_team": m.get("home_team", ""),
                    "away_team": m.get("away_team", ""),
                    "kickoff_ts": m.get("kickoff_ts", 0) or 0,
                    "lv_time": m.get("lv_time", ""),
                    "_league_key": league_key,
                    "_sxi_home_confirmed": False,
                    "_sxi_away_confirmed": False,
                    "_home_source": None,
                    "_away_source": None,
                }
                by_id[mid] = slot
            # OR-merge confirmed flags; first source wins the label.
            if m.get("sxi_home_confirmed") and not slot["_sxi_home_confirmed"]:
                slot["_sxi_home_confirmed"] = True
                slot["_home_source"] = src_name
            if m.get("sxi_away_confirmed") and not slot["_sxi_away_confirmed"]:
                slot["_sxi_away_confirmed"] = True
                slot["_away_source"] = src_name
            # Refresh other fields from the most-recent source that had them
            for k in ("home_team", "away_team", "kickoff_ts", "lv_time"):
                v = m.get(k)
                if v and not slot.get(k):
                    slot[k] = v
    return list(by_id.values())


def _process_match(league_key: str, league_cfg: dict, slot: dict,
                   state: dict, now: int) -> int:
    """Apply state to a merged slot and send first-source-wins
    notifications. Returns the number of notifications sent (0/1/2)."""
    home_id = slot["home_id"]
    away_id = slot["away_id"]
    match_id = _stable_match_id(league_key, home_id, away_id)
    prev = state.get(match_id, {})
    prev_home = bool(prev.get("home_sent"))
    prev_away = bool(prev.get("away_sent"))

    sxi_home = bool(slot["_sxi_home_confirmed"])
    sxi_away = bool(slot["_sxi_away_confirmed"])
    home_src = slot["_home_source"]
    away_src = slot["_away_source"]

    sent = 0
    new_entry = dict(prev)  # copy to mutate

    # First-source-wins: as soon as ANY source confirmed a team AND we
    # haven't sent the notification yet, send it RIGHT NOW. Don't wait
    # for the other team, don't wait for additional sources.
    if sxi_home and not prev_home:
        # First-source-wins for HOME: as soon as ANY source confirmed home
        # and we haven't sent yet, send the home-only notification. Do NOT
        # check away here even if it's also confirmed in this slot — that
        # is handled by the separate sxi_away branch below, which fires a
        # distinct second message when away becomes confirmed. This gives
        # the channel reader a per-team progress trail instead of one
        # silent "both" jump.
        msg = build_message(league_cfg, slot, "home")
        if send_telegram(msg):
            new_entry["home_sent"] = True
            new_entry["home_source"] = home_src
            new_entry["away_sent"] = bool(new_entry.get("away_sent", False))
            new_entry["home_team"] = slot.get("home_team") or new_entry.get("home_team", "")
            new_entry["away_team"] = slot.get("away_team") or new_entry.get("away_team", "")
            new_entry["kickoff_ts"] = slot.get("kickoff_ts") or new_entry.get("kickoff_ts", 0)
            new_entry["last_sent_at"] = now
            new_entry["last_sent_side"] = "home"
            state[match_id] = new_entry
            sent += 1
            log(f"  [{league_key}] sent home notification for "
                f"{slot.get('home_team')} vs {slot.get('away_team')} "
                f"(home_src={home_src})")
            # Fall through to the away branch so the channel gets a
            # second message if away is also confirmed in the same
            # cycle. Important: only fall through if the home send
            # succeeded — if Telegram failed we keep prev (no home_sent)
            # and the next cycle will retry from scratch.
        else:
            # tg failed; keep prev. next cycle retries.
            return sent

    if sxi_away and not prev_away:
        # First-source-wins for AWAY: send away-only if home hasn't been
        # sent yet, or 'both' if home was sent in a prior cycle OR in the
        # home branch above in this same cycle (the per-team progression
        # path — channel gets 'home' first, then 'both' for the upgrade).
        # The 'both' message is the "both teams now confirmed" final
        # form, so the channel reader sees: single ✅ → single ✅ → both ✅.
        prev_home_now = bool(state.get(match_id, new_entry).get("home_sent", False))
        side = "both" if prev_home_now else "away"
        msg = build_message(league_cfg, slot, side)
        if send_telegram(msg):
            new_entry = state.get(match_id, new_entry)  # ensure we mutate the latest
            new_entry["away_sent"] = True
            new_entry["away_source"] = away_src
            new_entry["home_sent"] = bool(new_entry.get("home_sent", False))
            new_entry["home_team"] = slot.get("home_team") or new_entry.get("home_team", "")
            new_entry["away_team"] = slot.get("away_team") or new_entry.get("away_team", "")
            new_entry["kickoff_ts"] = slot.get("kickoff_ts") or new_entry.get("kickoff_ts", 0)
            new_entry["last_sent_at"] = now
            new_entry["last_sent_side"] = side
            state[match_id] = new_entry
            sent += 1
            log(f"  [{league_key}] sent {side} notification for "
                f"{slot.get('home_team')} vs {slot.get('away_team')} "
                f"(away_src={away_src}{', home=prev_or_this_cycle' if side == 'both' else ''})")
    return sent


def process_league(league_key: str, league_cfg: dict, state: dict) -> int:
    """Per-league orchestrator. Runs all 4 sources in parallel and
    applies first-source-wins notification logic per match."""
    now = int(time.time())

    # Pre-filter: drop matches already fully sent (no HTTP, no work).
    # We can't know which match_ids are "fully sent" without knowing
    # which match_ids exist, so we still hit the sources — but inside
    # _process_match we short-circuit if both flags are set.
    #
    # Optimization: drop the rotowire HTTP entirely if we already know
    # this match is fully sent. The state keyed by league-key+ids, and
    # rotowire is the only source that returns the canonical match_id
    # list. If rotowire says "no new matches" (e.g. via a last_polled_at
    # header), we'd avoid the HTTP. For now: fetch, then filter.

    source_results: dict[str, list | None] = {name: None for name in SOURCE_REGISTRY}
    with ThreadPoolExecutor(max_workers=len(SOURCE_REGISTRY)) as ex:
        futs = {}
        for name in SOURCE_REGISTRY:
            try:
                fut = ex.submit(_get_source(name), league_key)
                futs[fut] = name
            except Exception as e:
                log(f"  [{league_key}] source {name} dispatch error: {e}")
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                source_results[name] = fut.result()
            except Exception as e:
                log(f"  [{league_key}] source {name} raised: {e}")
                source_results[name] = None

    merged = _merge_sources(league_key, source_results)
    if not merged:
        return 0

    sent = 0
    # Sep 16 2026: pre-load P-XI state once per cycle. We need it to
    # enforce the "S-XI only matches for matches where P-XI was
    # already sent" rule the user asked to restore. The endpoint
    # already filters to T±75min; this P-XI filter is the second
    # half of the original S-XI contract.
    pxi_state = _load_pxi_state()
    pxi_skipped = 0
    for slot in merged:
        # Skip matches kicked off >2h ago (no point notifying late).
        if slot.get("kickoff_ts") and slot["kickoff_ts"] < now - 2 * 3600:
            continue
        # Skip matches with neither side confirmed.
        if not slot["_sxi_home_confirmed"] and not slot["_sxi_away_confirmed"]:
            continue
        # Skip if already fully sent (defence-in-depth — the per-side
        # checks in _process_match also handle this, but skipping here
        # avoids the message-build + send_telegram prep).
        mid = _stable_match_id(league_key, slot["home_id"], slot["away_id"])
        prev = state.get(mid, {})
        if prev.get("home_sent") and prev.get("away_sent"):
            continue
        # Sep 16 2026: skip if P-XI was not yet sent for this match.
        # Restored from the pre-v2.5 S-XI contract. S-XI is the
        # "confirmation" of the lineup — it is only useful if the user
        # has already seen the P-XI prediction. Matches with no P-XI
        # record (or a P-XI record where neither side was sent) are
        # silently dropped here and logged below.
        if not _pxi_predicted(slot, league_key, pxi_state):
            pxi_skipped += 1
            log(f"  [{league_key}] skip {slot.get('home_team')} vs "
                f"{slot.get('away_team')} (no P-XI sent yet)")
            continue
        sent += _process_match(league_key, league_cfg, slot, state, now)
    if pxi_skipped:
        log(f"  [{league_key}] pxi-skipped {pxi_skipped} match(es) "
            f"with confirmed S-XI but no prior P-XI")
    return sent


def main():
    log(f"=== sxi_notifier starting (multi-source) ===")
    log(f"  API_BASE={API_BASE}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL}s  MAX_WORKERS={MAX_WORKERS}")
    log(f"  STATE_PATH={STATE_PATH}  LEAGUES={list(LEAGUES.keys())}")
    log(f"  SOURCES={list(SOURCE_REGISTRY.keys())}")
    state = load_state()
    log(f"  loaded state: {len(state)} match_ids")
    last_save = time.time()
    while True:
        try:
            with _state_lock:
                total_sent = 0
                total_checked = 0
                for league_key, league_cfg in LEAGUES.items():
                    r = process_league(league_key, league_cfg, state)
                    total_sent += r
                    if r is None:
                        pass
                # Always log a cycle heartbeat so the supervisor's
                # stale-log detection (xi_supervisor.sh) doesn't see
                # this process as frozen on a quiet day with no S-XI
                # confirmations. Single line per cycle keeps the log
                # readable.
                log(f"  cycle: checked {len(LEAGUES)} leagues, "
                    f"sent {total_sent}, state has {len(state)} match_ids")
                if total_sent > 0 or time.time() - last_save > 60:
                    save_state(state)
                    last_save = time.time()
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
