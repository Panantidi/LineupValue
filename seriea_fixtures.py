"""
Serie A fixtures fetcher using flashscore4 API.
Modeled after laliga_fixtures.py.

Aug 29 2026.
"""
import json
import os
import time
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

# Use the same RapidAPI credentials as LaLiga
from laliga_fixtures import HOST, HEADERS

CACHE_DIR = '/home/openclaw/.openclaw/workspace'
CACHE_PATH = os.path.join(CACHE_DIR, '_fixtures_seriea.json')
ROUND_CACHE_PATH = os.path.join(CACHE_DIR, '_fixtures_seriea_rounds.json')

MAX_FIXTURES_RETURN = 100
FIXTURES_TTL = 24 * 3600  # 24 hours

# Serie A team IDs from leagues_data.json
SERIEA_TEAM_IDS = [
    '0M9xNN8N',  # Bologna
    '4YSMlwj7',  # Monza
    '69Dxbc61',  # Napoli
    '6DxlaxHN',  # Parma
    '8C9JjMXu',  # Atalanta
    '8Sa8HInO',  # AC Milan
    'C06aJvIB',  # Juventus
    'G8lYsMgU',  # Lecce
    'Iw7eKK25',  # Inter
    'MZFZnvX4',  # Torino
    'MkPmVv50',  # Venezia
    'Q3A3IbXH',  # Fiorentina
    'QDdvI0zl',  # Sassuolo
    'SCGVmKHb',  # Cagliari
    'URcSl02h',  # Lazio
    'd0PJxeie',  # Genoa
    'pfo9H1Wp',  # Frosinone
    'rXw8YKDE',  # Udinese
    'ttyLthOA',  # Como
    'zVqqL0ma',  # AS Roma
]


def _http_get_json(url: str) -> Optional[Dict]:
    """HTTP GET with RapidAPI headers, return parsed JSON or None on error."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, Exception):
        return None


def _fixtures_cache_path() -> str:
    return CACHE_PATH


def _round_cache_path() -> str:
    return ROUND_CACHE_PATH


def _read_fixtures_cache() -> Optional[Dict]:
    p = _fixtures_cache_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    fetched_at = data.get('fetched_at') or 0
    if (time.time() - fetched_at) > FIXTURES_TTL:
        return None
    return data


def _write_fixtures_cache(payload: Dict) -> None:
    p = _fixtures_cache_path()
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _read_round_cache() -> Dict[str, str]:
    p = _round_cache_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_round_cache(round_map: Dict[str, str]) -> None:
    p = _round_cache_path()
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(round_map, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _fetch_team_fixtures(team_id: str) -> Optional[Dict]:
    """Fetch fixtures for a single Serie A team from flashscore4."""
    url = f"https://{HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
    return _http_get_json(url)


def _matches_from_team_response(team_id: str, raw: List[Dict]) -> List[Dict]:
    """Convert flashscore team fixtures response to our match format."""
    matches = []
    # raw is a list of tournaments
    for tournament in raw:
        tour_matches = tournament.get('matches', [])
        for ev in tour_matches:
            mid = ev.get('match_id')
            if not mid:
                continue
            
            home = ev.get('home_team', {})
            away = ev.get('away_team', {})
            
            home_id = home.get('team_id')
            away_id = away.get('team_id')
            
            ts = ev.get('timestamp')
            
            # Determine if this team is home or away
            is_home = (home_id == team_id)
            
            match = {
                'match_id': mid,
                'home': {
                    'id': home_id,
                    'name': home.get('name', ''),
                    'slug': home.get('short_name', ''),
                },
                'away': {
                    'id': away_id,
                    'name': away.get('name', ''),
                    'slug': away.get('short_name', ''),
                },
                'timestamp': ts,
                'round': '',  # will be filled by background resolver
                'status': {},  # flashscore4 doesn't include status in team fixtures
            }
            matches.append(match)
    
    return matches


def get_seriea_fixtures(force: bool = False) -> Dict:
    """Return upcoming Serie A matches with round info."""
    if not force:
        cached = _read_fixtures_cache()
        if cached and cached.get('fixtures'):
            return cached
    
    seen = set()
    aggregated = []
    
    for team_id in SERIEA_TEAM_IDS:
        raw = _fetch_team_fixtures(team_id)
        if raw is None:
            continue
        for m in _matches_from_team_response(team_id, raw):
            mid = m.get('match_id')
            if not mid or mid in seen:
                continue
            seen.add(mid)
            aggregated.append(m)
    
    aggregated.sort(key=lambda x: x.get('timestamp') or 0)
    
    # Stamp known rounds from disk cache
    round_cache = _read_round_cache()
    for m in aggregated:
        mid = m.get('match_id')
        m['round'] = round_cache.get(mid, '') if mid else ''
    
    trimmed = aggregated[:MAX_FIXTURES_RETURN]
    
    payload = {
        'fixtures': trimmed,
        'team_count': len(SERIEA_TEAM_IDS),
        'fetched_at': time.time(),
    }
    _write_fixtures_cache(payload)
    
    # Background round resolution
    threading.Thread(
        target=_background_resolve_rounds,
        args=(trimmed,),
        daemon=True,
    ).start()
    
    return payload


def _background_resolve_rounds(fixtures: List[Dict]) -> None:
    """Fill in the round field for matches missing it."""
    round_cache = _read_round_cache()
    updated = False
    
    for m in fixtures:
        mid = m.get('match_id')
        if not mid or mid in round_cache:
            continue
        
        # Fetch match details to get round info
        url = f"https://{HOST}/api/flashscore/v2/matches/details?match_id={mid}"
        raw = _http_get_json(url)
        if raw is None:
            continue
        
        # raw is a list of tournaments, find the match
        match = None
        for tournament in raw:
            for ev in tournament.get('matches', []):
                if ev.get('match_id') == mid:
                    match = ev
                    break
            if match:
                break
        
        if not match:
            continue
        
        round_info = match.get('roundInfo', {})
        round_text = round_info.get('round', '') or round_info.get('name', '')
        
        if round_text:
            round_cache[mid] = round_text
            updated = True
            print(f"Serie A round resolved: {mid} -> {round_text}")
        
        time.sleep(0.2)  # rate limit
    
    if updated:
        _write_round_cache(round_cache)


if __name__ == '__main__':
    import sys
    force = '--force' in sys.argv
    data = get_seriea_fixtures(force=force)
    print(f"Serie A fixtures: {len(data.get('fixtures', []))} matches")
    for m in data.get('fixtures', [])[:10]:
        home = m.get('home', {}).get('name', '?')
        away = m.get('away', {}).get('name', '?')
        ts = m.get('timestamp', 0)
        round_text = m.get('round', '?')
        print(f"  {home} vs {away} | ts={ts} | round={round_text}")
