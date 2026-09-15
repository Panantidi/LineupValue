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

    # Flashscore. Stubs for now. Suggested path when ready:
    # Flashscore. Pulls /teams/fixtures per LV team, then
    # /matches/match/lineups for each fixture in the T-75min window.
    # See source_flashscore() below. Implementation added Sep 16 2026.
    "flashscore": "source_flashscore",

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


# ---------------------------------------------------------------------
# Flashscore integration (Sep 16 2026)
# ---------------------------------------------------------------------
#
# Uses api_refresh.py's _fetch and HOST/HEADERS so we share one set of
# credentials with the rest of the project. The Rapidapi key is the
# same one used by /lineup_ai/api/fetch/{team_id} in app.py — it
# lives in api_refresh.py:13 (also exposed via env FS_RAPIDAPI_KEY
# if the operator wants to override without touching the file).
#
# Per-league flow:
#   1) Read leagues_data.json → LV teams for this league.
#   2) /api/flashscore/v2/teams/fixtures?team_id={lv_id}
#      → upcoming matches per team. Cached 5 min per team_id.
#   3) For each unique FS match_id whose kickoff is in [now-75m, now+75m],
#      call /api/flashscore/v2/matches/match/lineups?match_id={fs_mid}
#      → array of {side: "home"|"away", startingLineups: [11], substitutes: [~6], formation, missingPlayers}.
#   4) If a side has startingLineups with >= 11 items → that side is
#      confirmed. Mark sxi_*_confirmed=True and return rotowire-shaped
#      match dict so _merge_sources() can join this with rotowire by
#      (home_id, away_id).
#
# Performance / rate-limit notes:
#   - /teams/fixtures: 1 call per team in the league, cached 5 min.
#     Worst case: 7 leagues * 24 teams = 168 calls per process
#     lifetime (every 5 min) = ~3 calls/min — well below rapidapi
#     free tier.
#   - /matches/match/lineups: 1 call per unique FS match in T-75min.
#     Usually 0-15 calls/cycle (depends on fixture density).
#   - ThreadPoolExecutor elsewhere in process_league parallelises
#     across sources; here we do per-team sequential loops because
#     api_refresh._fetch already does retries + sleep(0.3) and we'd
#     risk rate-limiting if we fan out too wide.

_FS_HOST = None
_fs_fetch = None
_fs_fixtures_cache: dict = {}  # team_id -> (fetched_at, flat_list)
_fs_lineups_cache: dict = {}   # fs_match_id -> (fetched_at, lineups_list)
_FS_FIXTURES_TTL = 300  # 5 min
_FS_LINEUPS_TTL = 30    # 30s — we want fresh lineups, but not hammer the API
_FS_WINDOW_SEC = 75 * 60  # match kickoff in [now-75m, now+75m]
_FS_LV_LEAGUES_PATH = "/home/openclaw/FormAlert/leagues_data.json"
_lv_leagues_cache: dict | None = None  # in-memory; leagues_data.json is huge (400KB) so we load once


def _ensure_fs_imports():
    """Lazy-import api_refresh (only when flashscore is first used)."""
    global _FS_HOST, _fs_fetch
    if _fs_fetch is not None:
        return True
    try:
        sys.path.insert(0, "/home/openclaw/FormAlert")
        from api_refresh import _fetch, HOST  # type: ignore
        _fs_fetch = _fetch
        _FS_HOST = HOST
        # Allow env override of the api_refresh-embedded key without
        # touching api_refresh.py. If FS_RAPIDAPI_KEY is set we
        # monkey-patch HEADERS in the imported module for this process.
        override = os.environ.get("FS_RAPIDAPI_KEY")
        if override:
            import api_refresh  # type: ignore
            api_refresh.HEADERS["X-Rapidapi-Key"] = override
        return True
    except Exception as e:
        log(f"  [flashscore] api_refresh import failed: {e}")
        return False


def _load_lv_leagues() -> dict:
    global _lv_leagues_cache
    if _lv_leagues_cache is not None:
        return _lv_leagues_cache
    try:
        with open(_FS_LV_LEAGUES_PATH, "r", encoding="utf-8") as f:
            _lv_leagues_cache = json.load(f)
    except Exception as e:
        log(f"  [flashscore] leagues_data.json load failed: {e}")
        _lv_leagues_cache = {}
    return _lv_leagues_cache


def _fs_team_fixtures(team_id: str, now: int) -> list:
    """Cached /teams/fixtures for one team. Returns flat list
    (m, tname_short, tname_full)."""
    cached = _fs_fixtures_cache.get(team_id)
    if cached and (now - cached[0]) < _FS_FIXTURES_TTL:
        return cached[1]
    url = f"https://{_FS_HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
    d = _fs_fetch(url)
    if not d:
        _fs_fixtures_cache[team_id] = (now, [])
        return []
    rows = d if isinstance(d, list) else d.get("data", [])
    flat = []
    for env in (rows if isinstance(rows, list) else []):
        if not isinstance(env, dict):
            continue
        tshort = env.get("name") or ""
        tfull = env.get("full_name") or ""
        for m in env.get("matches", []) or []:
            if isinstance(m, dict):
                flat.append((m, tshort, tfull))
    _fs_fixtures_cache[team_id] = (now, flat)
    return flat


def _fs_match_lineups(fs_match_id: str, now: int) -> list:
    """Cached /matches/match/lineups. Returns list of side-envelope dicts."""
    cached = _fs_lineups_cache.get(fs_match_id)
    if cached and (now - cached[0]) < _FS_LINEUPS_TTL:
        return cached[1]
    url = f"https://{_FS_HOST}/api/flashscore/v2/matches/match/lineups?match_id={fs_match_id}"
    d = _fs_fetch(url)
    lineups = d if isinstance(d, list) else []
    _fs_lineups_cache[fs_match_id] = (now, lineups)
    return lineups


def source_flashscore(league_key: str):
    """LIVE source: Flashscore API (RapidAPI).

    Returns a list of rotowire-shaped match dicts (each with
    home_id, away_id, home_team, away_team, kickoff_ts,
    sxi_home_confirmed, sxi_away_confirmed) for matches in the
    T±75min window. Returns None if api_refresh couldn't be imported
    (caller will treat None as 'source unavailable').
    """
    if not _ensure_fs_imports():
        return None
    cfg = LEAGUES.get(league_key)
    if not cfg:
        return None
    country, league_name = cfg["country"], cfg["league"]
    lv_leagues = _load_lv_leagues()
    teams = lv_leagues.get(country, {}).get(league_name, [])
    if not teams:
        return None  # league not in our data

    now = int(time.time())
    # Pass 1: collect unique FS match_ids in T-75min window.
    seen: set = set()
    matches_to_check: list = []
    for t in teams:
        tid = t.get("id")
        if not tid:
            continue
        flat = _fs_team_fixtures(tid, now)
        for m, _tshort, _tfull in flat:
            mid = m.get("match_id")
            if not mid or mid in seen:
                continue
            ts = int(m.get("timestamp", 0) or 0)
            if not (now - _FS_WINDOW_SEC <= ts <= now + _FS_WINDOW_SEC):
                continue
            ht = m.get("home_team") or {}
            at = m.get("away_team") or {}
            h_id = (ht.get("team_id") if isinstance(ht, dict) else None) or ""
            a_id = (at.get("team_id") if isinstance(at, dict) else None) or ""
            h_name = (ht.get("name") if isinstance(ht, dict) else str(ht or ""))
            a_name = (at.get("name") if isinstance(at, dict) else str(at or ""))
            seen.add(mid)
            matches_to_check.append((mid, h_id, a_id, h_name, a_name, ts))

    # Pass 2: for each unique match, check lineups.
    out: list = []
    for mid, h_id, a_id, h_name, a_name, ts in matches_to_check:
        lineups = _fs_match_lineups(mid, now)
        sxi_home = sxi_away = False
        for entry in lineups:
            if not isinstance(entry, dict):
                continue
            starting = entry.get("startingLineups") or entry.get("starting") or []
            if not isinstance(starting, list) or len(starting) < 11:
                continue
            if entry.get("side") == "home":
                sxi_home = True
            elif entry.get("side") == "away":
                sxi_away = True
        out.append({
            "home_id": h_id,
            "away_id": a_id,
            "home_team": h_name,
            "away_team": a_name,
            "kickoff_ts": ts,
            "lv_time": "",  # build_message will format from kickoff_ts
            "sxi_home_confirmed": sxi_home,
            "sxi_away_confirmed": sxi_away,
        })
    if matches_to_check:
        log(f"  [flashscore/{league_key}] checked {len(matches_to_check)} "
            f"match(es) in T±75m; {sum(1 for o in out if o['sxi_home_confirmed'] or o['sxi_away_confirmed'])} with confirmed sides")
    return out


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
        sent += _process_match(league_key, league_cfg, slot, state, now)
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
