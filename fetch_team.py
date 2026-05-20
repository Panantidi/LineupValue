#!/usr/bin/env python3
"""
Unified team data fetcher for Soccerway.
Usage: python fetch_team.py <team_id> [--full]
  --full: squad + enrichment + last3 + lineups
  without --full: only last3 + lineups (fast)

Score is parsed from lineups page <title> tag.
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

def parse_score_from_title(title):
    """Parse score from page title like 'BRE 1-1 ANG | Brest v Angers ...'"""
    # Pattern: "TEAM1 SCORE-SCORE TEAM2 | ..."
    m = re.search(r'(\w+)\s+(\d+)\s*-\s*(\d+)\s+(\w+)\s*\|', title)
    if m:
        abbr1, s1, s2, abbr2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        return s1, s2, abbr1, abbr2
    return None

async def fetch_and_parse_lineups(matches, known_surnames):
    """Fetch lineups for all matches with home/away + score from title"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context()
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        results = []
        for match in matches:
            if not match.url:
                results.append({'date': '', 'tournament': '', 'starters': [], 'substitutes': [], 'missing': [], 'captains': [], 'score': '', 'home_team': '', 'away_team': ''})
                continue

            mid = match.mid or ''
            if not mid:
                m = re.search(r'mid=([a-zA-Z0-9]+)', match.url)
                mid = m.group(1) if m else ''

            game_path = re.search(r'/game/([^?]+)', match.url)
            match_path = re.search(r'/match/([^?]+)', match.url)
            slug = game_path.group(1).rstrip('/') if game_path else (match_path.group(1).rstrip('/') if match_path else '')

            if slug and mid:
                url = f'{BASE}/game/{slug}/summary/lineups/?mid={mid}'
            elif slug:
                url = f'{BASE}/game/{slug}/summary/lineups/'
            else:
                url = match.url

            print(f'    Loading: {match.date} {match.tournament}')
            try:
                await page.goto(url, wait_until='load', timeout=30000)
                await page.wait_for_timeout(4000)
                # Scroll to load lazy content (Missing Players section)
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await page.wait_for_timeout(500)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(2000)
                html = await page.content()
            except Exception as e:
                print(f'    ERROR: {e}')
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': [], 'missing': [], 'captains': [], 'score': '', 'home_team': '', 'away_team': ''})
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # Parse score from <title>
            title_el = soup.find('title')
            title_text = title_el.get_text() if title_el else ''
            # "BRE 1-1 ANG | Brest v Angers 17/05/2026, Lineups - Soccerway"
            # or "MON 4-5 STR | Monaco v Strasbourg ..."
            score_info = parse_score_from_title(title_text)
            score_str = ''
            home_team_name = ''
            away_team_name = ''
            if score_info:
                s1, s2, abbr1, abbr2 = score_info
                # Get full names from "Team1 v Team2" part after |
                names_match = re.search(r'\|\s*([^v]+)\s+v\s+([^\d]+)', title_text)
                if names_match:
                    home_team_name = names_match.group(1).strip()
                    away_team_name = names_match.group(2).strip().split(',')[0].strip()
                    score_str = f"{home_team_name} {s1}-{s2} {away_team_name}"
                else:
                    score_str = f"{abbr1} {s1}-{s2} {abbr2}"
                print(f'    Score: {score_str}')

            # Find Starting Lineups
            start_span = soup.find('span', string=re.compile(r'Starting Lineups', re.I))
            if not start_span:
                print(f'    No Starting Lineups found')
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': [], 'missing': [], 'captains': [], 'score': score_str, 'home_team': home_team_name, 'away_team': away_team_name})
                continue

            start_sec = start_span.find_parent('div', class_='section') or start_span.find_parent('div')
            left_names, right_names = [], []
            left_parts = start_sec.select('[data-testid="wcl-lineupsParticipantGeneral-left"]') if start_sec else []
            right_parts = start_sec.select('[data-testid="wcl-lineupsParticipantGeneral-right"]') if start_sec else []

            for part in left_parts:
                el = part.select_one('span[class*="wcl-bold"]')
                if el: left_names.append(el.get_text(strip=True))
            for part in right_parts:
                el = part.select_one('span[class*="wcl-bold"]')
                if el: right_names.append(el.get_text(strip=True))

            # Home/away by surname matching
            left_match = sum(1 for n in left_names if get_surname(n) in known_surnames)
            right_match = sum(1 for n in right_names if get_surname(n) in known_surnames)
            is_home = left_match >= right_match
            our_side = 'left' if is_home else 'right'
            our_parts = left_parts if is_home else right_parts
            print(f'    {"HOME" if is_home else "AWAY"}: left={left_match} right={right_match} starters={len(left_names if is_home else right_names)}')

            # Captains
            our_captains = set()
            for part in our_parts:
                if '(C)' in part.get_text():
                    el = part.select_one('span[class*="wcl-bold"]')
                    if el: our_captains.add(get_surname(el.get_text(strip=True)))

            # Substitutes
            our_subs = []
            sub_span = soup.find('span', string=re.compile(r'Substitutes', re.I))
            if sub_span:
                sub_sec = sub_span.find_parent('div', class_='section') or sub_span.find_parent('div')
                if sub_sec:
                    for part in sub_sec.select(f'[data-testid="wcl-lineupsParticipantGeneral-{our_side}"]'):
                        el = part.select_one('span[class*="wcl-bold"]')
                        if el: our_subs.append(el.get_text(strip=True))

            # Missing
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
                                    reason = txt; break
                            our_missing.append({'name': full_name, 'reason': reason})

            results.append({
                'date': match.date, 'tournament': match.tournament,
                'starters': left_names if is_home else right_names,
                'substitutes': our_subs, 'missing': our_missing,
                'captains': list(our_captains),
                'score': score_str, 'home_team': home_team_name, 'away_team': away_team_name
            })
            print(f'    -> starters={len(results[-1]["starters"])} subs={len(our_subs)} missing={len(our_missing)}')

        await browser.close()
    return results

def apply_last3(players, lineups_data):
    for p in players:
        surname = get_surname(p['name'])
        last3, last3_missing, last3_captain = [], [], []
        for ld in lineups_data:
            found = False
            for s in ld.get('starters', []):
                if get_surname(s) == surname:
                    last3.append('START')
                    last3_captain.append(surname in ld.get('captains', []))
                    last3_missing.append(None)
                    found = True; break
            if found: continue
            for s in ld.get('substitutes', []):
                if get_surname(s) == surname:
                    last3.append('SUB')
                    last3_captain.append(False)
                    last3_missing.append(None)
                    found = True; break
            if found: continue
            for m in ld.get('missing', []):
                if get_surname(m.get('name', '')) == surname:
                    last3.append('')
                    last3_captain.append(False)
                    last3_missing.append(m.get('reason', ''))
                    found = True; break
            if not found:
                last3.append('-')
                last3_captain.append(False)
                last3_missing.append(None)
        while len(last3) < 3:
            last3.append('-'); last3_captain.append(False); last3_missing.append(None)
        p['last3'] = last3[:3]
        p['last3_missing'] = last3_missing[:3]
        p['last3_captain'] = last3_captain[:3]
    return players

async def run_full(team_id, team_name, team_slug, coach_nat='', stadium=''):
    from soccerway_parser import get_squad_page, parse_squad_html, enrich_players_async, get_last3_matches
    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'

    print(f'[1/5] Squad: {team_name}...')
    html = await get_squad_page(team_id, team_name)
    players_raw, coach_name, _ = parse_squad_html(html, team_id)
    print(f'  {len(players_raw)} players')

    print('[2/5] Enriching...')
    players_raw = await enrich_players_async(players_raw, concurrency=1)
    players = []
    for p in players_raw:
        d = dict(p) if isinstance(p, dict) else vars(p)
        for old, new in {'minutes':'min','goals':'goal','assists':'assist','yellow_cards':'yellow_card','red_cards':'red_card','player_url':'profile_path'}.items():
            if old in d and new not in d: d[new] = d.pop(old)
        players.append(d)
    enriched = sum(1 for p in players if p.get('market_value') or p.get('position'))
    print(f'  Enriched: {enriched}/{len(players)}')
    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    cache = {'team': {'id': team_id, 'name': team_name, 'slug': team_slug},
             'coach': {'name': coach_name, 'nationality': coach_nat}, 'stadium': stadium,
             'players': players, '_cached_at': time.time(), 'last_updated': time.time()}
    with open(cache_path, 'w') as f: json.dump(cache, f, indent=2, ensure_ascii=False)
    print('  [saved enrichment]')

    print('[3/5] Last 3 matches...')
    matches = await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')

    print('[4/5] Lineups + scores...')
    lineups_data = await fetch_and_parse_lineups(matches, known_surnames)

    print('[5/5] Applying...')
    players = apply_last3(players, lineups_data)
    m1s = sum(1 for p in players if p.get('last3',[])[0:1]==['START'])
    m2s = sum(1 for p in players if len(p.get('last3',[]))>1 and p['last3'][1]=='START')
    m3s = sum(1 for p in players if len(p.get('last3',[]))>2 and p['last3'][2]=='START')
    print(f'  START: m1={m1s} m2={m2s} m3={m3s}')

    cache['players'] = players
    cache['matches'] = [{'date': m.date, 'tournament': m.tournament, 'url': m.url, 'mid': m.mid,
                         'score': ld.get('score',''), 'home_team': ld.get('home_team',''), 'away_team': ld.get('away_team','')}
                        for m, ld in zip(matches, lineups_data)]
    cache['_cached_at'] = time.time()
    cache['last_updated'] = time.time()
    with open(cache_path, 'w') as f: json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f'\nDone! {len(players)} players, {len(cache["matches"])} matches')
    for m in cache['matches']:
        print(f'  {m["date"]} {m["tournament"]}: {m.get("score","?")}')

async def run_last3_only(team_id, team_name):
    from soccerway_parser import get_last3_matches
    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
    with open(cache_path, 'r') as f: cache = json.load(f)
    players = cache['players']
    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    print('[1/3] Last 3 matches...')
    matches = await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')

    print('[2/3] Lineups + scores...')
    lineups_data = await fetch_and_parse_lineups(matches, known_surnames)

    print('[3/3] Applying...')
    players = apply_last3(players, lineups_data)

    cache['players'] = players
    cache['matches'] = [{'date': m.date, 'tournament': m.tournament, 'url': m.url, 'mid': m.mid,
                         'score': ld.get('score',''), 'home_team': ld.get('home_team',''), 'away_team': ld.get('away_team','')}
                        for m, ld in zip(matches, lineups_data)]
    cache['_cached_at'] = time.time()
    cache['last_updated'] = time.time()
    with open(cache_path, 'w') as f: json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f'Done!')
    for m in cache['matches']:
        print(f'  {m["date"]} {m["tournament"]}: {m.get("score","?")}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python fetch_team.py <team_id> [--full --team-name "Name" --slug "slug" --coach-nat "Country" --stadium "Stadium"]')
        sys.exit(1)

    team_id = sys.argv[1]
    args = sys.argv[2:]
    full_mode = '--full' in args
    def get_arg(name, default=''):
        for i, a in enumerate(args):
            if a == name and i+1 < len(args): return args[i+1]
        return default

    team_name = get_arg('--team-name', '')
    team_slug = get_arg('--slug', '')
    coach_nat = get_arg('--coach-nat', '')
    stadium = get_arg('--stadium', '')

    if full_mode:
        if not team_name: print('ERROR: --full requires --team-name'); sys.exit(1)
        asyncio.run(run_full(team_id, team_name, team_slug, coach_nat, stadium))
    else:
        if not team_name:
            try:
                with open(f'{CACHE_DIR}/_live_cache_{team_id}.json') as f:
                    team_name = json.load(f).get('team',{}).get('name','')
            except: pass
        if not team_name: print('ERROR: need --team-name or existing cache'); sys.exit(1)
        asyncio.run(run_last3_only(team_id, team_name))
