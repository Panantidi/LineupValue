"""On-demand refresh from Flashscore API (no Soccerway).
Refreshes squad + last 3 matches + lineups + player_details for a team.
"""
import json
import os
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- Config ---
KEY = "82f1fc4f2emsh6f172ea91bb5386p1cd344jsndd0fc401e69f"
HOST = "flashscore4.p.rapidapi.com"
HEADERS = {
    "X-Rapidapi-Key": KEY,
    "X-Rapidapi-Host": HOST,
    "User-Agent": "curl/8.5.0",
    "Accept": "*/*",
}
CACHE_DIR = "/home/openclaw/.openclaw/workspace"
LEAGUES_FILE = "/home/openclaw/FormAlert/leagues_data.json"

# --- Cache TTL ---
CACHE_TTL_SECONDS = 600  # 10 minutes

# --- Lock to prevent concurrent refreshes for the same team ---
_refresh_in_progress = set()

# --- Slug cache (populated lazily) ---
_slug_cache = {}


def _get_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch(url, retries=2):
    """Fetch URL with retry. Returns dict/list or None."""
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=_get_ssl(), timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.3)
    return None


def _cache_path(team_id):
    return os.path.join(CACHE_DIR, f"_live_cache_{team_id}.json")


def _read_cache(team_id):
    """Read existing cache, or empty dict if missing/corrupt."""
    p = _cache_path(team_id)
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(team_id, data):
    """Write cache atomically."""
    p = _cache_path(team_id)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.rename(tmp, p)


def _get_team_info(team_id):
    """Find team info in leagues_data.json. Returns (country, champ, slug) or None."""
    if team_id in _slug_cache:
        return _slug_cache[team_id]
    try:
        with open(LEAGUES_FILE) as f:
            ld = json.load(f)
    except Exception:
        return None
    for country, champs in ld.items():
        for champ, teams in champs.items():
            for t in teams:
                if t.get("id") == team_id:
                    info = (country, champ, t.get("slug") or team_id)
                    _slug_cache[team_id] = info
                    return info
    _slug_cache[team_id] = None
    return None


def _cache_age_seconds(team_id):
    """Return age of cache in seconds, or None if no cache."""
    p = _cache_path(team_id)
    if not os.path.exists(p):
        return None
    try:
        return time.time() - os.path.getmtime(p)
    except Exception:
        return None


def is_fresh(team_id, ttl=CACHE_TTL_SECONDS):
    """Return True if cache is fresh (age < TTL)."""
    age = _cache_age_seconds(team_id)
    if age is None:
        return False
    return age < ttl


def refresh_squad(team_id, slug, info):
    """Fetch /teams/squad and return parsed players list (or None)."""
    url = f"https://{HOST}/api/flashscore/v2/teams/squad?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    data = _fetch(url)
    if not data:
        return None
    groups = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(groups, list) or not groups:
        return []
    players = []
    # Prefer first group with a list (top-tier league)
    best_group = None
    for g in groups:
        if isinstance(g, dict) and g.get("list"):
            best_group = g
            break
    if best_group:
        tab_name = best_group.get("tab_name", "")
        for section in best_group["list"]:
            if not isinstance(section, dict):
                continue
            grp_name = section.get("name", "")
            for p in section.get("players", []):
                pid = p.get("player_id")
                name = p.get("name")
                if not pid or not name:
                    continue
                players.append({
                    "player_id": pid,
                    "name": name,
                    "position": grp_name,
                    "age": int(p["age"]) if p.get("age", "").isdigit() else None,
                    "nationality": p.get("country_name", ""),
                    "country": p.get("country_name", ""),
                    "number": p.get("number"),
                    "market_value": None,  # filled by player_details
                    "matches_played": int(p["matches_played"]) if p.get("matches_played", "").isdigit() else 0,
                    "minutes_played": int(p["minutes_played"]) if p.get("minutes_played", "").isdigit() else 0,
                    "goals": int(p["goals_scored"]) if p.get("goals_scored", "").isdigit() else 0,
                    "assists": int(p["assists"]) if p.get("assists", "").isdigit() else 0,
                    "yellow_cards": int(p["yellow_cards"]) if p.get("yellow_cards", "").isdigit() else 0,
                    "red_cards": int(p["red_cards"]) if p.get("red_cards", "").isdigit() else 0,
                    "player_url": p.get("player_url", ""),
                    "tournament": tab_name,
                })
    return players


def refresh_player_details(player, delay=0.25):
    """Fetch /players/details and update market_value, image_path, etc."""
    purl = player.get("player_url", "")
    if not purl:
        return
    # purl is like "/player/qirko-pano/vBb94SxF/"
    full_url = f"https://{HOST}/api/flashscore/v2/players/details?player_url={urllib.parse.quote(purl, safe='/?=')}"
    d = _fetch(full_url)
    if not d or not isinstance(d, dict):
        return
    mv = d.get("market_value")
    if mv:
        player["market_value"] = mv
    img = d.get("image_path")
    if img:
        player["image_path"] = img
    stats = d.get("statistics") or d.get("stats") or {}
    if isinstance(stats, dict):
        for k in ["goals", "assists", "yellow_cards", "red_cards", "matches_played", "minutes_played"]:
            if k in stats:
                player[k] = stats[k]
    time.sleep(delay)


def refresh_results(team_id):
    """Fetch /teams/results and return list of last 3 matches (with lineups)."""
    url = f"https://{HOST}/api/flashscore/v2/teams/results?team_id={team_id}&page=1"
    data = _fetch(url)
    if not data:
        return []
    # data structure: list of matches with home/away/score/timestamp/teams
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(rows, list):
        return []
    matches = []
    for m in rows[:3]:
        if not isinstance(m, dict):
            continue
        # Try to extract match_id and teams
        mid = m.get("id") or m.get("match_id") or m.get("MatchId")
        home = m.get("home_team") or m.get("home") or {}
        away = m.get("away_team") or m.get("away") or {}
        # home/away can be dict {id, name, slug} or string
        def _team_info(t):
            if isinstance(t, dict):
                return {
                    "id": t.get("id") or t.get("team_id"),
                    "name": t.get("name") or t.get("short_name") or t.get("full_name"),
                }
            return {"id": None, "name": str(t) if t else ""}
        home_info = _team_info(home)
        away_info = _team_info(away)
        # Score
        score = m.get("score") or m.get("ft_score") or ""
        if not score and isinstance(m.get("home_score"), int):
            score = f"{m.get('home_score')}-{m.get('away_score')}"
        # Tournament
        tname = m.get("tournament_name") or m.get("tournament") or ""
        tshort = m.get("tournament_short_name") or m.get("tournament_name_short") or ""
        # Timestamp
        ts = m.get("timestamp") or m.get("start_timestamp") or 0
        # Date
        date_str = ""
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts))
                date_str = dt.strftime("%d/%m")
            except Exception:
                pass
        matches.append({
            "date": date_str,
            "timestamp": int(ts) if ts else 0,
            "tournament_name_short": tshort,
            "tournament_name_full": tname,
            "home_team": home_info["name"] or "",
            "home_team_id": home_info["id"] or "",
            "away_team": away_info["name"] or "",
            "away_team_id": away_info["id"] or "",
            "score": score,
            "match_id": mid,
        })
    return matches


def refresh_lineups_for_matches(matches, team_id):
    """For each match, fetch /lineups and attach to match dict."""
    for m in matches:
        mid = m.get("match_id")
        if not mid:
            continue
        url = f"https://{HOST}/api/flashscore/v2/matches/match/lineups?match_id={mid}"
        d = _fetch(url)
        if not d or not isinstance(d, dict):
            continue
        # Parse lineups: looking for our team's lineup
        lineups = d.get("lineups") or d.get("data") or []
        if isinstance(lineups, list):
            for lu in lineups:
                if not isinstance(lu, dict):
                    continue
                lu_team_id = lu.get("team_id") or lu.get("id")
                if str(lu_team_id) == str(team_id):
                    players = lu.get("players") or lu.get("starting") or []
                    if isinstance(players, list):
                        m["lineup_player_ids"] = [str(p.get("player_id") or p.get("id")) for p in players if (p.get("player_id") or p.get("id"))]
        time.sleep(0.2)


def refresh_team(team_id, force=False):
    """Sync refresh: fetch squad + last 3 + lineups + player_details from Flashscore API.
    Returns True if cache was updated, False otherwise (already fresh, in-progress, or error).
    """
    if team_id in _refresh_in_progress:
        return False
    if not force and is_fresh(team_id):
        return False
    info = _get_team_info(team_id)
    if not info:
        return False
    country, champ, slug = info
    _refresh_in_progress.add(team_id)
    try:
        # 1. Squad
        players = refresh_squad(team_id, slug, info)
        if players is None:
            return False
        # 2. Last 3 matches
        matches = refresh_results(team_id)
        # 3. Lineups for matches
        refresh_lineups_for_matches(matches, team_id)
        # 4. Player details (market_value, image) - parallel
        if players:
            with ThreadPoolExecutor(max_workers=2) as ex:
                list(ex.map(refresh_player_details, players))
        # 5. Build cache
        cache = _read_cache(team_id)  # preserve existing keys (coach, stadium, etc.)
        cache["team"] = {
            "id": team_id,
            "name": cache.get("team", {}).get("name", ""),
            "country": country,
            "championship": champ,
            "slug": slug,
        }
        cache["players"] = players
        cache["matches"] = matches
        cache["last_updated"] = datetime.now().isoformat()
        _write_cache(team_id, cache)
        return True
    finally:
        _refresh_in_progress.discard(team_id)


def ensure_fresh_async(team_id):
    """Trigger background refresh if cache is stale. Safe to call from request handler."""
    if team_id in _refresh_in_progress:
        return
    if is_fresh(team_id):
        return
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(asyncio.to_thread(refresh_team, team_id))
    except RuntimeError:
        # No event loop - spawn thread
        import threading
        t = threading.Thread(target=refresh_team, args=(team_id,), daemon=True)
        t.start()
