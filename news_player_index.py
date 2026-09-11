"""
news_notifier_player_index.py — Sep 11 2026
Loads /home/openclaw/.openclaw/workspace/_live_cache_*.json files and
builds:
  - player_name (normalized) -> {"team_id": ..., "team_name": ...}
  - team_id -> {"team_name": ..., "next_match": {...}}

Then build_message uses this index to:
  1. Extract player name from RSS title
  2. Find the player's team
  3. Pick the next (upcoming) match
  4. Format: <b>title</b> + body + "TeamA - TeamB (link)" line
"""
import json
import os
import re
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get(
    "NEWS_LV_CACHE_DIR",
    "/home/openclaw/.openclaw/workspace",
))
# Filter only SOCCER cache files (other sports have their own format)
# Cache files for soccer: e.g. lId4TMwf, kZ8xTCSq, etc. (10-char LV ids)
CACHE_GLOB = "_live_cache_*.json"
# Cached index file location (rebuilt every 30 min in process)
INDEX_PATH = Path("/home/openclaw/FormAlert/data/news_player_index.json")
INDEX_TTL_SEC = 30 * 60  # 30 min

_player_index = None  # normalized name -> {"team_id", "team_name"}
_team_index = None    # team_id -> {"team_name", "fixtures": [...]}
_index_built_at = 0


def _normalize_name(name):
    """Return a tuple of possible normalized names for fuzzy lookup.
    Handles both 'Cody Gakpo' (RSS title) and 'Gakpo Cody' (LV cache).
    Returns up to 2 keys: ('gakpo cody', 'cody gakpo') for a 2-token name.
    """
    s = re.sub(r"\s+", " ", (name or "").strip().lower())
    parts = s.split(" ")
    if len(parts) >= 2:
        a = " ".join(parts)            # "cody gakpo"
        b = f"{parts[-1]} {' '.join(parts[:-1])}"  # "gakpo cody"
        if a == b:
            return (a,)
        return (a, b)
    return (s,)


def _build_index():
    """Scan CACHE_DIR/_live_cache_*.json and build name + team indexes.
    Returns (player_index, team_index).

    player_index maps normalized name -> list of {"team_id", "team_name",
    "player_name"}. We keep ALL teams a player appears in, so the
    resolver can pick the most relevant one (e.g. club over national
    team).
    """
    player_index = {}
    team_index = {}
    if not CACHE_DIR.is_dir():
        return player_index, team_index
    for path in CACHE_DIR.glob(CACHE_GLOB):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        team = d.get("team") or {}
        team_id = team.get("id")
        team_name = team.get("name", "")
        if not team_id or not team_name:
            continue
        fixtures = d.get("fixtures") or []
        team_index[team_id] = {
            "team_name": team_name,
            "fixtures": fixtures,
        }
        for p in d.get("players", []):
            pname = (p.get("name") or "").strip()
            pid = (p.get("player_id") or "").strip()
            if not pname:
                continue
            # If the player is in a cache whose team name is a country
            # but the player has a `club` attribute, they're misfiled —
            # the cache represents the player's national team but lists
            # club players. We still keep the entry (so the resolver
            # can decide), but mark is_country_cached=True.
            is_country_cached = _is_country_name(team_name)
            for norm in _normalize_name(pname):
                if not norm:
                    continue
                player_index.setdefault(norm, []).append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "player_name": pname,
                    "player_id": pid,
                    "is_country_cached": is_country_cached,
                })
    return player_index, team_index


def _load_index(force_reload=False):
    """Load the player+team index. Rebuilds from disk if older than TTL
    or if force_reload=True. Caches in memory + INDEX_PATH.
    """
    global _player_index, _team_index, _index_built_at
    now = time.time()
    if (not force_reload and _player_index is not None
            and (now - _index_built_at) < INDEX_TTL_SEC):
        return _player_index, _team_index
    # Try disk cache first
    if not force_reload and INDEX_PATH.exists():
        try:
            age = now - INDEX_PATH.stat().st_mtime
            if age < INDEX_TTL_SEC:
                with open(INDEX_PATH, encoding="utf-8") as f:
                    blob = json.load(f)
                _player_index = blob.get("players", {})
                _team_index = blob.get("teams", {})
                _index_built_at = now
                return _player_index, _team_index
        except (OSError, json.JSONDecodeError):
            pass
    # Rebuild from disk
    _player_index, _team_index = _build_index()
    _index_built_at = now
    # Persist
    try:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "players": _player_index,
                "teams": _team_index,
                "built_at": int(now),
                "player_count": len(_player_index),
                "team_count": len(_team_index),
            }, f, ensure_ascii=False)
    except OSError:
        pass
    return _player_index, _team_index


def find_player_team(player_name):
    """Look up the team for a given player name. Returns
    {"team_id", "team_name", "player_id"} or None.

    Resolution strategy (in order of preference):
      1. Team whose next match's lineup_player_ids contains the
         player's ID. Ground truth — confirms the player is in the
         next XI.
      2. Team (other than a country name) with the soonest upcoming
         fixture. Falls back to this when no lineup data is available.
      3. Any team (last resort).
    """
    if not player_name:
        return None
    p_idx, t_idx = _load_index()
    candidates = []
    for norm in _normalize_name(player_name):
        for entry in p_idx.get(norm, []) or []:
            candidates.append(entry)
    if not candidates:
        return None
    if len(candidates) == 1:
        info = candidates[0]
        pid = info.get("player_id", "")
        return {"team_id": info["team_id"], "team_name": info["team_name"],
                "player_id": pid}

    # Multiple candidates — find best.
    now = time.time()
    lineup_hits = []  # confirmed in next XI
    clubs = []        # non-country teams
    all_cands = []
    for info in candidates:
        team = t_idx.get(info["team_id"]) or {}
        pid = info.get("player_id", "")
        # Check matches (in chronological order, find first upcoming)
        upcoming_match = None
        upcoming_ts = None
        for m in team.get("fixtures", []):
            ts = m.get("timestamp") or 0
            if ts > now and (upcoming_ts is None or ts < upcoming_ts):
                upcoming_ts = ts
                upcoming_match = m
        if not upcoming_match:
            upcoming_ts = now + 365 * 24 * 3600  # de-prioritize
        is_club = not _is_country_name(info["team_name"])
        # A country-cached player is more likely to actually play
        # for their club (national team has fewer matches and is
        # less relevant for "next match" link).
        is_misfiled = bool(info.get("is_country_cached"))
        entry = (info, upcoming_match, upcoming_ts, is_club, is_misfiled)
        all_cands.append(entry)
        if upcoming_match and pid in (upcoming_match.get("lineup_player_ids") or []):
            lineup_hits.append(entry)
        if is_club:
            clubs.append(entry)

    # 1. Lineup hit is the gold standard
    pool = lineup_hits or clubs or all_cands
    # Sort: soonest match first, prefer club, de-prioritize country-cached
    pool.sort(key=lambda e: (e[2], 0 if e[3] else 1, 0 if not e[4] else 1))
    info, _, _, _, _ = pool[0]
    return {"team_id": info["team_id"], "team_name": info["team_name"],
            "player_id": info.get("player_id", "")}


# Known national team names (subset; full list is large). Used to
# detect and de-prioritize national teams when picking a club team.
_COUNTRY_NAMES = frozenset({
    "england", "spain", "france", "germany", "italy", "portugal",
    "netherlands", "belgium", "brazil", "argentina", "uruguay",
    "colombia", "mexico", "united states", "usa", "croatia", "poland",
    "denmark", "sweden", "norway", "switzerland", "austria", "turkey",
    "ukraine", "russia", "japan", "south korea", "australia", "iran",
    "saudi arabia", "qatar", "egypt", "morocco", "tunisia", "nigeria",
    "ghana", "senegal", "cameroon", "ivory coast", "algeria", "chile",
    "peru", "ecuador", "paraguay", "venezuela", "bolivia", "costa rica",
    "honduras", "panama", "jamaica", "trinidad and tobago", "iceland",
    "finland", "ireland", "scotland", "wales", "czech republic",
    "slovakia", "slovenia", "serbia", "montenegro", "albania",
    "north macedonia", "bosnia and herzegovina", "greece", "romania",
    "bulgaria", "hungary", "israel", "cyprus", "luxembourg", "malta",
    "estonia", "latvia", "lithuania", "belarus", "moldova", "georgia",
    "armenia", "azerbaijan", "kazakhstan", "uzbekistan", "china",
    "thailand", "vietnam", "indonesia", "malaysia", "singapore",
    "india", "pakistan", "bangladesh", "sri lanka", "nepal",
    "philippines", "myanmar", "cambodia", "laos", "mongolia",
    "new zealand", "fiji", "papua new guinea", "tonga", "samoa",
    "vanuatu", "solomon islands", "cook islands", "tahiti", "new caledonia",
    "south africa", "kenya", "ethiopia", "tanzania", "uganda", "zambia",
    "zimbabwe", "botswana", "namibia", "mozambique", "angola", "congo",
    "democratic republic of the congo", "gabon", "mali", "burkina faso",
    "guinea", "sierra leone", "liberia", "gambia", "mauritania",
    "benin", "togo", "niger", "chad", "central african republic",
    "equatorial guinea", "sao tome and principe", "cape verde",
    "seychelles", "mauritius", "comoros", "madagascar", "rwanda",
    "burundi", "south sudan", "eritrea", "djibouti", "somalia",
    "kuwait", "bahrain", "united arab emirates", "oman", "yemen",
    "jordan", "lebanon", "syria", "iraq", "palestine", "brunei",
    "taiwan", "hong kong", "macau", "north korea", "maldives",
    "bhutan", "afghanistan", "turkmenistan", "kyrgyzstan", "tajikistan",
    "east timor", "northern mariana islands", "guam", "american samoa",
})


def _is_country_name(name):
    return (name or "").strip().lower() in _COUNTRY_NAMES


def get_next_match(team_id):
    """Return the next upcoming match for the team, or None.
    Match dict: {"match_id", "home", "away", "home_id", "away_id",
                 "kickoff_ts", "date", "time"}.
    """
    if not team_id:
        return None
    _, t_idx = _load_index()
    team = t_idx.get(team_id)
    if not team:
        return None
    now = time.time()
    upcoming = []
    for f in team.get("fixtures", []):
        ts = f.get("timestamp") or 0
        if ts > now:
            upcoming.append((ts, f))
    if not upcoming:
        return None
    upcoming.sort(key=lambda x: x[0])
    _, f = upcoming[0]
    return {
        "match_id": f.get("match_id", ""),
        "home": f.get("home_team", ""),
        "away": f.get("away_team", ""),
        "home_id": f.get("home_team_id", ""),
        "away_id": f.get("away_team_id", ""),
        "kickoff_ts": f.get("timestamp", 0),
        "date": f.get("date", ""),
        "time": f.get("time", ""),
    }


def extract_player_from_title(title):
    """RSS titles look like 'Cody Gakpo: Uncertain for Fulham clash' or
    'Bradley Barcola: Forced off with cramp Wednesday'. Extract the
    leading name (up to first colon).
    """
    if not title:
        return ""
    m = re.match(r"^\s*([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)+)\s*:", title)
    if m:
        return m.group(1).strip()
    return ""


def make_compare_url(home_id, away_id, home_name, away_name, match_id):
    """Build the /lineup_ai/compare/{team_id}?... URL the user wants."""
    import urllib.parse
    params = {
        "mid": match_id,
        "home_id": home_id,
        "away_id": away_id,
        "home_name": home_name,
        "away_name": away_name,
    }
    # team_id in the URL is the home team (consistent with SXI/PXI)
    base = os.environ.get("NEWS_SITE_BASE", "https://x11radar.ru")
    return (f"{base}/lineup_ai/compare/{home_id}?"
            + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
