#!/usr/bin/env python3
"""
Unified team data fetcher for Soccerway.
Usage: python fetch_team.py <team_id> [--full]
  --full: also fetch enrichment (slow, ~3 min)
  without --full: only fetch last3 + lineups (fast, ~1 min)

Needs pre-existing cache with squad data.
"""
import asyncio, json, re, time, sys
sys.path.insert(0, '/home/openclaw/FormAlert')

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

BASE = 'https://us.soccerway.com'
CACHE_DIR = '/home/openclaw/.openclaw/workspace'

def get_surname(name):
    parts = name.strip().split()
    return parts[0].lower().rstrip('.') if parts else ''

async def fetch_and_parse_lineups(matches, known_surnames):
    """Fetch lineups for all matches with proper home/away detection via content matching"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context()
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        results = []
        for match in matches:
            if not match.url:
                results.append({'date': '', 'tournament': '', 'starters': [], 'substitutes': [], 'missing': [], 'captains': []})
                continue

            mid = match.mid or ''
            if not mid:
                m = re.search(r'mid=([a-zA-Z0-9]+)', match.url)
                mid = m.group(1) if m else ''

            game_path = re.search(r'/game/([^?]+)', match.url)
            slug = game_path.group(1).rstrip('/') if game_path else ''

            if slug and mid:
                url = f'{BASE}/game/{slug}/summary/lineups/?mid={mid}'
            else:
                url = match.url

            print(f'    Loading: {match.date} {match.tournament}')
            try:
                await page.goto(url, wait_until='load', timeout=30000)
                await page.wait_for_timeout(8000)
                html = await page.content()
            except Exception as e:
                print(f'    ERROR: {e}')
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': [], 'missing': [], 'captains': []})
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # Find Starting Lineups section
            start_span = soup.find('span', string=re.compile(r'Starting Lineups', re.I))
            if not start_span:
                print(f'    No Starting Lineups found')
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': [], 'missing': [], 'captains': []})
                continue

            start_sec = start_span.find_parent('div', class_='section') or start_span.find_parent('div')

            # Extract left/right names
            left_names = []
            right_names = []
            left_parts = start_sec.select('[data-testid="wcl-lineupsParticipantGeneral-left"]') if start_sec else []
            right_parts = start_sec.select('[data-testid="wcl-lineupsParticipantGeneral-right"]') if start_sec else []

            for part in left_parts:
                el = part.select_one('span[class*="wcl-bold"]')
                if el:
                    left_names.append(el.get_text(strip=True))
            for part in right_parts:
                el = part.select_one('span[class*="wcl-bold"]')
                if el:
                    right_names.append(el.get_text(strip=True))

            # Determine home/away by surname matching
            left_match = sum(1 for n in left_names if get_surname(n) in known_surnames)
            right_match = sum(1 for n in right_names if get_surname(n) in known_surnames)
            is_home = left_match >= right_match
            our_side = 'left' if is_home else 'right'
            our_names = left_names if is_home else right_names
            our_parts = left_parts if is_home else right_parts
            side_label = 'HOME (left)' if is_home else 'AWAY (right)'
            print(f'    {side_label}: left={left_match} right={right_match} starters={len(our_names)}')

            # Captains
            our_captains = set()
            for part in our_parts:
                text = part.get_text()
                el = part.select_one('span[class*="wcl-bold"]')
                if el and '(C)' in text:
                    our_captains.add(get_surname(el.get_text(strip=True)))

            # Substitutes
            our_subs = []
            sub_span = soup.find('span', string=re.compile(r'Substitutes', re.I))
            if sub_span:
                sub_sec = sub_span.find_parent('div', class_='section') or sub_span.find_parent('div')
                if sub_sec:
                    for part in sub_sec.select(f'[data-testid="wcl-lineupsParticipantGeneral-{our_side}"]'):
                        el = part.select_one('span[class*="wcl-bold"]')
                        if el:
                            our_subs.append(el.get_text(strip=True))

            # Missing Players
            our_missing = []
            miss_span = soup.find('span', string=re.compile(r'Missing Players', re.I))
            if miss_span:
                miss_sec = miss_span.find_parent('div', class_='section') or miss_span.find_parent('div')
                if miss_sec:
                    for part in miss_sec.select(f'[data-testid="wcl-lineupsParticipantGeneral-{our_side}"]'):
                        el = part.select_one('span[class*="wcl-bold"]')
                        if el:
                            full_name = el.get_text(strip=True)
                            reason = ''
                            for span in part.select('span'):
                                txt = span.get_text(strip=True)
                                if txt and txt != full_name and len(txt) > 2 and not txt.startswith('('):
                                    reason = txt
                                    break
                            our_missing.append({'name': full_name, 'reason': reason})

            results.append({
                'date': match.date,
                'tournament': match.tournament,
                'starters': our_names,
                'substitutes': our_subs,
                'missing': our_missing,
                'captains': list(our_captains)
            })
            print(f'    -> starters={len(our_names)} subs={len(our_subs)} missing={len(our_missing)} captains={list(our_captains)}')

        await browser.close()
    return results

def apply_last3(players, lineups_data):
    """Apply last3 + missing + captain to players"""
    for p in players:
        surname = get_surname(p['name'])
        last3 = []
        last3_missing = []
        last3_captain = []
        for ld in lineups_data:
            found = False
            # Starters
            for s in ld.get('starters', []):
                if get_surname(s) == surname:
                    last3.append('START')
                    last3_captain.append(surname in ld.get('captains', []))
                    last3_missing.append(None)
                    found = True
                    break
            if found: continue
            # Substitutes
            for s in ld.get('substitutes', []):
                if get_surname(s) == surname:
                    last3.append('SUB')
                    last3_captain.append(False)
                    last3_missing.append(None)
                    found = True
                    break
            if found: continue
            # Missing
            for m in ld.get('missing', []):
                if get_surname(m.get('name', '')) == surname:
                    last3.append('')
                    last3_captain.append(False)
                    last3_missing.append(m.get('reason', ''))
                    found = True
                    break
            if not found:
                last3.append('-')
                last3_captain.append(False)
                last3_missing.append(None)

        while len(last3) < 3:
            last3.append('-')
            last3_captain.append(False)
            last3_missing.append(None)
        p['last3'] = last3[:3]
        p['last3_missing'] = last3_missing[:3]
        p['last3_captain'] = last3_captain[:3]
    return players

async def run_full(team_id, team_name, team_slug, coach_nat='', stadium=''):
    """Full pipeline: squad + enrichment + last3 + lineups"""
    from soccerway_parser import (
        get_squad_page, parse_squad_html, enrich_players_async,
        get_last3_matches
    )

    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'

    # Step 1-2: Squad + Enrichment
    print(f'[1/5] Fetching squad for {team_name}...')
    html = await get_squad_page(team_id, team_name)
    players_raw, coach_name, _ = parse_squad_html(html, team_id)
    print(f'  {len(players_raw)} players')

    print('[2/5] Enriching (MV, Pos)...')
    players_raw = await enrich_players_async(players_raw, concurrency=1)

    # Convert to dicts
    players = []
    for p in players_raw:
        d = dict(p) if isinstance(p, dict) else vars(p)
        key_map = {'minutes':'min','goals':'goal','assists':'assist',
                   'yellow_cards':'yellow_card','red_cards':'red_card','player_url':'profile_path'}
        for old, new in key_map.items():
            if old in d and new not in d:
                d[new] = d.pop(old)
        players.append(d)

    enriched = sum(1 for p in players if p.get('market_value') or p.get('position'))
    print(f'  Enriched: {enriched}/{len(players)}')

    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    # Save intermediate
    cache = {
        'team': {'id': team_id, 'name': team_name, 'slug': team_slug},
        'coach': {'name': coach_name, 'nationality': coach_nat},
        'stadium': stadium,
        'players': players,
        '_cached_at': time.time(),
        'last_updated': time.time()
    }
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    print('  [enrichment saved]')

    # Step 3: Results
    print('[3/5] Last 3 matches...')
    matches = await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')

    # Step 4: Lineups
    print('[4/5] Lineups...')
    lineups_data = await fetch_and_parse_lineups(matches, known_surnames)

    # Step 5: Apply + Save
    print('[5/5] Applying...')
    players = apply_last3(players, lineups_data)

    m1s = sum(1 for p in players if p.get('last3',[])[0:1]==['START'])
    m2s = sum(1 for p in players if len(p.get('last3',[]))>1 and p['last3'][1]=='START')
    m3s = sum(1 for p in players if len(p.get('last3',[]))>2 and p['last3'][2]=='START')
    print(f'  START per match: m1={m1s} m2={m2s} m3={m3s}')

    cache['players'] = players
    cache['matches'] = [{'date': m.date, 'tournament': m.tournament, 'url': m.url, 'mid': m.mid} for m in matches]
    cache['_cached_at'] = time.time()
    cache['last_updated'] = time.time()

    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f'\nDone! {len(players)} players, {len(cache["matches"])} matches')
    return cache

async def run_last3_only(team_id, team_name):
    """Fast: only re-fetch last3 + lineups for existing cache"""
    from soccerway_parser import get_last3_matches

    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
    with open(cache_path, 'r') as f:
        cache = json.load(f)
    players = cache['players']
    print(f'Loaded {len(players)} players from cache')

    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    print('[1/3] Last 3 matches...')
    matches = await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')

    print('[2/3] Lineups...')
    lineups_data = await fetch_and_parse_lineups(matches, known_surnames)

    print('[3/3] Applying...')
    players = apply_last3(players, lineups_data)

    cache['players'] = players
    cache['matches'] = [{'date': m.date, 'tournament': m.tournament, 'url': m.url, 'mid': m.mid} for m in matches]
    cache['_cached_at'] = time.time()
    cache['last_updated'] = time.time()

    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    m1s = sum(1 for p in players if p.get('last3',[])[0:1]==['START'])
    m2s = sum(1 for p in players if len(p.get('last3',[]))>1 and p['last3'][1]=='START')
    m3s = sum(1 for p in players if len(p.get('last3',[]))>2 and p['last3'][2]=='START')
    print(f'  START per match: m1={m1s} m2={m2s} m3={m3s}')
    print(f'Done!')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python fetch_team.py <team_id> [--full --team-name "Name" --slug "slug" --coach-nat "Country" --stadium "Stadium"]')
        sys.exit(1)

    team_id = sys.argv[1]
    args = sys.argv[2:]

    full_mode = '--full' in args

    def get_arg(name, default=''):
        for i, a in enumerate(args):
            if a == name and i+1 < len(args):
                return args[i+1]
        return default

    team_name = get_arg('--team-name', '')
    team_slug = get_arg('--slug', '')
    coach_nat = get_arg('--coach-nat', '')
    stadium = get_arg('--stadium', '')

    if full_mode:
        if not team_name:
            print('ERROR: --full requires --team-name')
            sys.exit(1)
        asyncio.run(run_full(team_id, team_name, team_slug, coach_nat, stadium))
    else:
        if not team_name:
            # Try to get from cache
            cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
            try:
                with open(cache_path, 'r') as f:
                    d = json.load(f)
                team_name = d.get('team', {}).get('name', '')
            except:
                pass
        if not team_name:
            print('ERROR: need --team-name or existing cache')
            sys.exit(1)
        asyncio.run(run_last3_only(team_id, team_name))
