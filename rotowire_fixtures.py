"""
rotowire.com fixtures fetcher for 5 leagues (EPL, UCL, FRAN, BUND, MLS).

Sep 3 2026 — new Predicted XI source modeled on seriea_fixtures.py.

Pages: https://www.rotowire.com/soccer/lineups.php (EPL default),
?league=UCL / FRAN / BUND / MLS.

Each fixture carries a placeholder match_id ('rotowire_<league>_...') that
is later replaced by the real LineupValue (flashscore) match_id once the
fixture is matched to a LV team fixture within 2 days.
"""
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Optional

# Use the same RapidAPI credentials as LaLiga / Serie A
from laliga_fixtures import HOST, HEADERS

CACHE_DIR = '/home/openclaw/.openclaw/workspace'
CACHE_PATH = os.path.join(CACHE_DIR, '_fixtures_rotowire.json')
PAGE_TTL = 6 * 3600  # 6 hours per league page

DEFAULT_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
)

# ET (Eastern Time) = UTC-5 — fixed offset, no timezonefinder needed.
ET = ZoneInfo("America/New_York")  # Sep 6 2026 — DST-aware (EDT in summer, EST in winter)

# league key -> {'name': panel display name, 'url': full URL}
ROTOWIRE_LEAGUES = {
    'epl':  {'name': 'Premier League',
             'url': 'https://www.rotowire.com/soccer/lineups.php'},
    'ucl':  {'name': 'Champions League',
             'url': 'https://www.rotowire.com/soccer/lineups.php?league=UCL'},
    'fran': {'name': 'Ligue 1',
             'url': 'https://www.rotowire.com/soccer/lineups.php?league=FRAN'},
    'bund': {'name': 'Bundesliga',
             'url': 'https://www.rotowire.com/soccer/lineups.php?league=BUND'},
    'mls':  {'name': 'MLS',
             'url': 'https://www.rotowire.com/soccer/lineups.php?league=MLS'},
}


def _name_eq(a: str, b: str) -> bool:
    """Fuzzy team-name match (NFD strip + token containment), same as app.py."""
    import unicodedata
    def _strip(s: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', s)
                       if unicodedata.category(c) != 'Mn')
    al = _strip((a or '').lower())
    bl = _strip((b or '').lower())
    if not al or not bl:
        return False
    if al == bl:
        return True
    if al in bl or bl in al:
        return True
    at = al.replace('.', '').replace('-', ' ').split()
    bt = bl.replace('.', '').replace('-', ' ').split()
    return any(t and (t in bt or bt[0].startswith(t) or t.startswith(bt[0]))
               for t in at)


def fetch_page(league_key: str, max_age: int = PAGE_TTL) -> Optional[str]:
    """Fetch (or cache-load) the rotowire lineup page for one league."""
    pages = _page_cache_read()
    entry = pages.get(league_key)
    if entry and max_age and (time.time() - (entry.get('fetched_at') or 0)) <= max_age:
        return entry.get('html')
    url = ROTOWIRE_LEAGUES[league_key]['url']
    req = urllib.request.Request(url, headers={'User-Agent': DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception:
        return entry.get('html') if entry else None
    pages[league_key] = {'html': html, 'fetched_at': int(time.time())}
    try:
        _page_cache_write(pages)
    except Exception:
        pass
    return html


def _page_cache_read() -> Dict[str, Dict[str, Any]]:
    """Read cached league pages. Returns {league_key: {'html', 'fetched_at'}}."""
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _page_cache_write(pages: Dict[str, Dict[str, Any]]) -> None:
    tmp = CACHE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def parse_league_page(league_key: str, html: str) -> List[Dict[str, Any]]:
    """Parse one league page into fixture dicts (no LV team ids yet).

    Each fixture:
        {'match_id': placeholder, 'league': key, 'tournament': display name,
         'home': {'name': full}, 'away': {'name': full},
         'date_label', 'time_label', 'timestamp'}
    """
    out = []
    blocks = re.split(r'<div class="lineup is-soccer">', html)[1:]
    for block in blocks:
        time_m = re.search(
            r'<div class="lineup__time"><b>([^<]+)</b>&nbsp;\s*([^<]+)</div>',
            block)
        if not time_m:
            continue
        date_label = time_m.group(1)
        time_label = time_m.group(2)
        home_m = re.search(r'<div class="lineup__mteam is-home">([^<]+)<span',
                           block)
        away_m = re.search(r'<div class="lineup__mteam is-visit">([^<]+)<span',
                           block)
        if not home_m or not away_m:
            continue
        home_name = home_m.group(1).strip()
        away_name = away_m.group(1).strip()
        ts = _parse_et_time(date_label, time_label)
        slug_name = f'{home_name}-{away_name}'.replace(' ', '-')
        out.append({
            'match_id': f'rotowire_{league_key}_{slug_name}',
            'league': league_key,
            'tournament': ROTOWIRE_LEAGUES[league_key]['name'],
            'home': {'name': home_name},
            'away': {'name': away_name},
            'date_label': date_label,
            'time_label': time_label,
            'timestamp': ts,
        })
    return out


def _parse_et_time(date_label: str, time_label: str) -> int:
    """Parse 'September 4' + '3:00 PM ET' -> epoch (ET = UTC-5).

    Dates without a year are assumed to be in the current year; if the
    parsed date is more than 180 days behind now, assume next year
    (rotowire lists dates close to today, this only guards the rollover).
    """
    months = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November',
              'December']
    m = re.match(r'([A-Za-z]+) (\d{1,2})', date_label)
    if not m or m.group(1) not in months:
        return 0
    month = months.index(m.group(1)) + 1
    day = int(m.group(2))
    year = datetime.now().year
    try:
        dt = datetime(year, month, day, tzinfo=ET)
    except ValueError:
        return 0
    now = datetime.now(ET)
    if (now - dt).days > 180:
        try:
            dt = datetime(year + 1, month, day, tzinfo=ET)
        except ValueError:
            return 0
    tm = re.match(r'(\d{1,2}):(\d{2}) (AM|PM) ET', time_label)
    if not tm:
        return 0
    hh = int(tm.group(1))
    mm = int(tm.group(2))
    if tm.group(3) == 'PM' and hh != 12:
        hh += 12
    if tm.group(3) == 'AM' and hh == 12:
        hh = 0
    dt = datetime(dt.year, dt.month, dt.day, hh, mm, tzinfo=ET)
    return int(dt.timestamp())


def _load_team_id_map() -> Dict[str, str]:
    """Build team name -> id map from ALL leagues in leagues_data.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'leagues_data.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    map: Dict[str, str] = {}
    for country, champs in data.items():
        for champ, teams in champs.items():
            for t in teams:
                name = t.get('name') or ''
                id = t.get('id') or ''
                if name and id:
                    map[name] = id
    return map


def _find_team_id(map: Dict[str, str], name: str) -> Optional[str]:
    """Find a team id via _name_eq against the map names."""
    best = None
    for mn, id in map.items():
        if _name_eq(mn, name):
            best = id
            break
    return best


def _attach_lv_match_ids(fixtures: List[Dict[str, Any]]) -> None:
    """Attach real LV match_ids from flashscore team fixtures.

    Match rotowire fixture (home_id, away_id, date proximity <= 2 days)
    to LV fixtures -> attach real match_id. Drop unmatched.
    """
    team_ids: Dict[str, str] = {}
    for f in fixtures:
        hid = f.get('home', {}).get('id')
        aid = f.get('away', {}).get('id')
        if hid:
            team_ids[hid] = hid
        if aid:
            team_ids[aid] = aid

    lv_fixtures: Dict[str, List[Dict]] = {}
    for team_id in team_ids:
        url = f"https://{HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = json.load(resp)
        except Exception:
            continue
        lv_list = []
        for tournament in raw:
            tour_matches = tournament.get('matches', []) or []
            for ev in tour_matches:
                mid = ev.get('match_id')
                if not mid:
                    continue
                lv_list.append({
                    'match_id': mid,
                    'home_id': ev.get('home_team', {}).get('team_id'),
                    'away_id': ev.get('away_team', {}).get('team_id'),
                    'timestamp': ev.get('timestamp'),
                })
        lv_fixtures[team_id] = lv_list

    for f in fixtures:
        hid = f.get('home', {}).get('id')
        aid = f.get('away', {}).get('id')
        ts = int(f.get('timestamp') or 0)
        real_mid = None
        candidates = (lv_fixtures.get(hid) or []) + (lv_fixtures.get(aid) or [])
        for c in candidates:
            cts = int(c.get('timestamp') or 0)
            if not cts:
                continue
            if abs(cts - ts) > 2 * 3600 * 24:
                continue
            # Must match the rotowire fixture's home/away sides.
            if hid and c.get('home_id') != hid and c.get('away_id') != hid:
                continue
            if aid and c.get('home_id') != aid and c.get('away_id') != aid:
                continue
            real_mid = c.get('match_id')
            break
        if real_mid:
            f['match_id'] = real_mid


def get_rotowire_fixtures(force: bool = False) -> Dict:
    """Return upcoming rotowire matches with real LV team ids + match_ids."""
    all_fixtures: List[Dict[str, Any]] = []
    for league_key in ROTOWIRE_LEAGUES:
        try:
            html = fetch_page(league_key)
        except Exception:
            html = None
        if not html:
            continue
        all_fixtures.extend(parse_league_page(league_key, html))

    map = _load_team_id_map()
    out = []
    for f in all_fixtures:
        hid = _find_team_id(map, f['home']['name'])
        aid = _find_team_id(map, f['away']['name'])
        if not hid or not aid:
            continue
        f['home'] = {'name': f['home']['name'], 'id': hid, 'team_id': hid}
        f['away'] = {'name': f['away']['name'], 'id': aid, 'team_id': aid}
        out.append(f)

    try:
        _attach_lv_match_ids(out)
    except Exception:
        pass

    # Drop fixtures still carrying a placeholder match_id (unmatched).
    out = [f for f in out if f.get('match_id') and
           not f.get('match_id').startswith('rotowire_')]
    return {'fixtures': out}


# ---- Upcoming rounds via flashscore team fixtures (seriea pattern) ----
from seriea_fixtures import _fetch_team_fixtures as _fetch_fs_team_fixtures, _matches_from_team_response
ROTOWIRE_CHAMPS = {'epl': ('England', 'Premier League'), 'fran': ('France', 'Ligue 1'), 'bund': ('Germany', 'Bundesliga'), 'mls': ('USA', 'MLS')}





def _champ_team_ids() -> dict:
    """Per-league team ids from leagues_data.json (valid for querying)."""
    try:
        data = json.load(open('/home/openclaw/FormAlert/leagues_data.json'))
    except Exception:
        return {}
    out = {}
    for league_key, (country, champ) in ROTOWIRE_CHAMPS.items():
        ids = []
        ch = data.get(country, {})
        ch_list = ch.get(champ, []) if isinstance(ch, dict) else []
        for team_data in ch_list:
            team_id = team_data.get('id') if isinstance(team_data, dict) else None
            if team_id:
                ids.append(team_id)
        out[league_key] = ids
    return out








def get_upcoming_rounds() -> dict:
    """CURRENT round + NEXT round only, strictly Round from API."""
    team_ids_map = _champ_team_ids()
    now = time.time()
    seen = set()
    aggregated = []
    for league_key, ids in team_ids_map.items():
        if league_key not in ROTOWIRE_CHAMPS:
            continue
        league_tour = ROTOWIRE_CHAMPS[league_key][1]
        league_names = _champ_team_names(league_key)
        for team_id in ids:
            raw = _fetch_fs_team_fixtures(team_id)
            if raw is None:
                continue
            for tournament in raw:
                tour_name = tournament.get('name')
                if tour_name != league_tour:
                    continue
                for ev in tournament.get('matches', []):
                    mid = ev.get('match_id')
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    ts = ev.get('timestamp') or 0
                    if ts and ts < now:
                        continue
                    home = ev.get('home_team', {})
                    away = ev.get('away_team', {})
                    h_name = home.get('name')
                    a_name = away.get('name')
                    if h_name in league_names and a_name in league_names:
                        h_id = home.get('id')
                        a_id = away.get('id')
                        m = {'match_id': mid, 'tournament': league_tour, 'timestamp': ts}
                        m['home'] = {'id': h_id, 'name': h_name, 'team_id': h_id}
                        m['away'] = {'id': a_id, 'name': a_name, 'team_id': a_id}
                        aggregated.append(m)
    _enrich_rounds(aggregated[:60])
    with_round = [m for m in aggregated if m.get('round')]
    with_round.sort(key=lambda x: int(x.get('timestamp') or 0))
    r1 = with_round[0].get('round') if with_round else None
    r2 = None
    for m in with_round:
        if m.get('round') != r1:
            r2 = m.get('round')
            break
    keep = [m for m in with_round if m.get('round') == r1 or (r2 and m.get('round') == r2)]
    return {'fixtures': keep}
def _enrich_rounds(fixtures) -> None:
    """Round labels via matches/details endpoint (LaLiga/SerieA pattern)."""
    try:
        round_cache = json.load(open(ROUND_CACHE_PATH))
    except Exception:
        round_cache = {}
    try:
        from seriea_fixtures import _read_round_cache
    except Exception:
        _read_round_cache = None
    try:
        from laliga_fixtures import _parse_round_label
    except Exception:
        def _parse_round_label(name: str) -> str:
            return (name or '').strip()
    for m in fixtures:
        mid = m.get('match_id')
        if not mid:
            continue
        if mid in round_cache:
            m['round'] = round_cache[mid]
            continue
        try:
            from laliga_fixtures import HOST, HEADERS
            url = f"https://{HOST}/api/flashscore/v2/matches/details?match_id={mid}"
            req = urllib.request.Request(url, headers=HEADERS)
            details = json.loads(urllib.request.urlopen(req, timeout=20).read())
        except Exception:
            continue
        if not details:
            continue
        tournament = (details.get('tournament') or {})
        label = _parse_round_label(tournament.get('name') or '')
        if label:
            round_cache[mid] = label
            m['round'] = label
    try:
        json.dump(round_cache, open(ROUND_CACHE_PATH, 'w'))
    except Exception:
        pass
def _champ_team_names(league_key) -> set:
    """League team names from leagues_data.json."""
    names = set()
    try:
        data = json.load(open('/home/openclaw/FormAlert/leagues_data.json'))
        country, champ = ROTOWIRE_CHAMPS[league_key]
        ch = data.get(country, {})
        ch_list = ch.get(champ, []) if isinstance(ch, dict) else []
        for team_data in ch_list:
            if isinstance(team_data, dict) and team_data.get('name'):
                names.add(team_data.get('name'))
    except Exception:
        pass
    return names
