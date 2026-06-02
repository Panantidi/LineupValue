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

BASE = 'https://www.soccerway.com'
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
                url = f'{BASE}/match/{slug}/summary/lineups/?mid={mid}'
            elif slug:
                url = f'{BASE}/match/{slug}/summary/lineups/'
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

            # Captains — store full lineup name for disambiguation
            our_captains = []
            for part in our_parts:
                if '(C)' in part.get_text():
                    el = part.select_one('span[class*="wcl-bold"]')
                    if el: our_captains.append(el.get_text(strip=True))

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
                'captains_full': list(our_captains),
                'score': score_str, 'home_team': home_team_name, 'away_team': away_team_name
            })
            print(f'    -> starters={len(results[-1]["starters"])} subs={len(our_subs)} missing={len(our_missing)}')

        await browser.close()
    return results

def _is_captain(player_name, cap_fullnames):
    """Check if player is captain. cap_fullnames are full names from lineups
    like 'Martinez L.'. When surname is ambiguous, also check initial."""
    p_surname = get_surname(player_name)
    p_initials = [w[0].lower() for w in player_name.split() if w and w[0].isalpha()]
    for cap_name in cap_fullnames:
        cap_surname = get_surname(cap_name)
        if cap_surname != p_surname:
            continue
        # Surname matches — if lineup name has initial (e.g. "Martinez L.")
        # verify initial matches one of player's name parts
        cap_parts = cap_name.replace('.', ' ').split()
        cap_initials = [w[0].lower() for w in cap_parts if w and w[0].isalpha()]
        # If captain name only has surname + initial(s), check those initials
        if len(cap_parts) >= 2 and len(cap_initials) > 1:
            # Check if any initial from captain matches any non-surname part of player name
            for ci in cap_initials[1:]:  # skip surname initial
                if ci in p_initials[1:]:
                    return True
            return False  # surname matched but initials didn't
        # Only surname in captain name — accept
        return True
    return False

def _name_initials(name):
    cleaned = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ\s.-]', ' ', str(name or '')).replace('.', ' ')
    parts = [p for p in cleaned.split() if p]
    return [p[0].lower() for p in parts if p and p[0].isalpha()]


def _match_lineup_to_player(lineup_name, candidates):
    """Return one best roster player for a Soccerway lineup name.

    Soccerway often has abbreviated names like "Murphy A." while the cache has
    "Murphy Alex" and "Murphy Jacob". Matching every cache player by surname
    duplicates START circles. This function consumes each lineup entry once and
    disambiguates by initials when a surname is not unique.
    """
    l_surname = get_surname(lineup_name)
    if not l_surname:
        return None
    same_surname = [p for p in candidates if get_surname(p.get('name', '')) == l_surname]
    if not same_surname:
        return None
    if len(same_surname) == 1:
        return same_surname[0]

    l_parts = str(lineup_name or '').replace('.', ' ').split()
    l_extra_initials = _name_initials(' '.join(l_parts[1:])) if len(l_parts) > 1 else []
    if l_extra_initials:
        filtered = []
        for p in same_surname:
            p_parts = str(p.get('name', '') or '').split()
            p_extra_initials = _name_initials(' '.join(p_parts[1:])) if len(p_parts) > 1 else []
            if all(i in p_extra_initials for i in l_extra_initials):
                filtered.append(p)
        if len(filtered) == 1:
            return filtered[0]
        if filtered:
            same_surname = filtered

    # If Soccerway gives no usable initial for an ambiguous surname, choose the
    # player with the highest season minutes as the least damaging fallback.
    def mins(p):
        try:
            return int(str(p.get('min', 0) or 0).replace(',', ''))
        except Exception:
            return 0
    return sorted(same_surname, key=mins, reverse=True)[0]


def _assign_lineup_statuses(players, lineup_names):
    available = list(players)
    assigned = {}
    for lname in lineup_names or []:
        p = _match_lineup_to_player(lname, available)
        if not p:
            continue
        key = id(p)
        if key in assigned:
            continue
        assigned[key] = lname
        available.remove(p)
    return assigned


def apply_last3(players, lineups_data):
    # Reset arrays first.
    for p in players:
        p['last3'] = []
        p['last3_missing'] = []
        p['last3_captain'] = []

    for ld in lineups_data:
        cap_fullnames = ld.get('captains_full', ld.get('captains', []))
        starter_map = _assign_lineup_statuses(players, ld.get('starters', []))
        sub_map = _assign_lineup_statuses(
            [p for p in players if id(p) not in starter_map],
            ld.get('substitutes', [])
        )
        missing_entries = ld.get('missing', []) or []
        missing_names = [m.get('name', '') for m in missing_entries if isinstance(m, dict)]
        missing_map_players = _assign_lineup_statuses(
            [p for p in players if id(p) not in starter_map and id(p) not in sub_map],
            missing_names
        )
        missing_reason_by_player = {}
        for m in missing_entries:
            if not isinstance(m, dict):
                continue
            mp = _match_lineup_to_player(m.get('name', ''), [p for p in players if id(p) in missing_map_players])
            if mp:
                missing_reason_by_player[id(mp)] = m.get('reason', '')

        for p in players:
            key = id(p)
            if key in starter_map:
                p['last3'].append('START')
                p['last3_captain'].append(_is_captain(p['name'], cap_fullnames))
                p['last3_missing'].append(None)
            elif key in sub_map:
                p['last3'].append('SUB')
                p['last3_captain'].append(False)
                p['last3_missing'].append(None)
            elif key in missing_map_players:
                p['last3'].append('')
                p['last3_captain'].append(False)
                p['last3_missing'].append(missing_reason_by_player.get(key, ''))
            else:
                p['last3'].append('-')
                p['last3_captain'].append(False)
                p['last3_missing'].append(None)

    for p in players:
        while len(p['last3']) < 3:
            p['last3'].append('-'); p['last3_captain'].append(False); p['last3_missing'].append(None)
        p['last3'] = p['last3'][:3]
        p['last3_missing'] = p['last3_missing'][:3]
        p['last3_captain'] = p['last3_captain'][:3]
    return players

async def get_last3_matches_by_slug(team_id, team_name, team_slug, limit=6):
    """Fetch recent match candidates using official Soccerway slug from standings/overall.

    We fetch more than 3 candidates because Soccerway sometimes lists a match
    without lineup data (postponed/fixture/partial page). Later we keep the
    first 3 candidates that actually have parsed starting lineups.
    """
    from soccerway_parser import Match
    from playwright.async_api import async_playwright
    comp_map = {
        'bundesliga': 'BL', '2. bundesliga': 'B2', 'dfb pokal': 'DFB', 'league cup': 'LC',
        'ligue 1': 'L1', 'serie a': 'SA', 'la liga': 'LL', 'laliga': 'LL', 'premier league': 'PL',
        'conference league': 'ECL', 'europa league': 'EL', 'champions league': 'CL',
        'fa cup': 'FA', 'efl cup': 'LC', 'club friendlies': 'FR', 'friendlies': 'FR', 'friendly': 'FR',
    }
    url = f'{BASE}/team/{team_slug}/{team_id}/results/'
    print(f'  [Playwright] Loading configured results {url}')
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36', viewport={'width':1920,'height':1080}, locale='en-US')
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_timeout(5000)
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(500)
        html = await page.content()
        await browser.close()
    soup = BeautifulSoup(html, 'html.parser')
    matches=[]; seen=set()
    for a in soup.select('a[href*="/match/"], a[href*="/game/"]'):
        href=a.get('href','')
        if team_id not in href:
            continue
        mid_m=re.search(r'[?&]mid=([A-Za-z0-9]+)', href)
        mid=mid_m.group(1) if mid_m else ''
        if not mid or mid in seen:
            continue
        seen.add(mid)
        match_url = href if href.startswith('http') else f'{BASE}{href}'
        parent=a.find_parent('div', class_=re.compile(r'event__match'))
        parent_text=parent.get_text(' ', strip=True) if parent else a.get_text(' ', strip=True)
        date=''
        dm=re.search(r'(\d{1,2})\.(\d{2})\.', parent_text)
        if dm:
            date=f'{dm.group(1).zfill(2)}.{dm.group(2)}'
        league_div=a.find_parent('div', class_=re.compile(r'leagues'))
        header_text = ''
        if league_div and parent:
            current_header = None
            for child in league_div.find_all(['div', 'section'], recursive=False):
                classes = ' '.join(child.get('class', []))
                if 'headerLeague' in classes:
                    current_header = child.get_text(' ', strip=True)
                if child is parent:
                    header_text = current_header or ''
                    break
        if not header_text:
            # Fallback: only inspect nearby previous league headers, never the whole
            # leagues container (it can contain multiple competitions).
            header = parent.find_previous_sibling(class_=re.compile(r'headerLeague')) if parent else None
            header_text = header.get_text(' ', strip=True) if header else ''
        lt = header_text.lower()
        tournament = 'UNK'
        for key,val in comp_map.items():
            if key in lt:
                tournament=val; break
        matches.append(Match(date=date, tournament=tournament, mid=mid, url=match_url, score='', home_team='', away_team='', home_score=0, away_score=0))
        if len(matches) >= limit:
            break
    for m in matches:
        print(f'    {m.date} {m.tournament}: {m.url}')
    return matches

def _copy_existing_last3_fields(new_players, old_cache):
    """Preserve Last 3 fields from existing cache while a full refresh is in progress.

    Full refresh saves an intermediate enriched squad before lineups are parsed.
    Without this, opening the team during/after an incomplete full refresh can
    show blank Last 3. Match by exact name first, then one-to-one surname fallback.
    """
    old_players = list((old_cache or {}).get('players') or [])
    if not old_players:
        return new_players
    by_name = {str(p.get('name', '')).strip().lower(): p for p in old_players if p.get('name')}
    remaining_old = list(old_players)
    for p in new_players:
        old = by_name.get(str(p.get('name', '')).strip().lower())
        if not old:
            old = _match_lineup_to_player(p.get('name', ''), remaining_old)
        if old:
            for k, default in [('last3', ['-', '-', '-']), ('last3_missing', [None, None, None]), ('last3_captain', [False, False, False])]:
                p[k] = list(old.get(k) or default)[:3]
            if old in remaining_old:
                remaining_old.remove(old)
        else:
            p.setdefault('last3', ['-', '-', '-'])
            p.setdefault('last3_missing', [None, None, None])
            p.setdefault('last3_captain', [False, False, False])
    return new_players


async def run_full(team_id, team_name, team_slug, coach_nat='', stadium=''):
    from soccerway_parser import get_squad_page, parse_squad_html, enrich_players_async, get_last3_matches, Match
    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
    existing_cache = {}
    try:
        with open(cache_path, 'r') as f:
            existing_cache = json.load(f)
    except Exception:
        existing_cache = {}

    print(f'[1/5] Squad: {team_name}...')
    html = ''
    # get_squad_page builds slug from team_name, which fails for official Soccerway
    # slugs like 1-fc-koln or vfb-stuttgart. If --slug is provided, prefer it.
    if team_slug:
        from playwright.async_api import async_playwright
        url = f'https://www.soccerway.com/team/{team_slug}/{team_id}/squad/'
        print(f'  [Playwright] Loading configured slug {url}')
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
            context = await browser.new_context(user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36', viewport={'width':1920,'height':1080}, locale='en-US')
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(5000)
            html = await page.content()
            await browser.close()
    if not html:
        html = await get_squad_page(team_id, team_name)
    players_raw, coach_name, stadium_from_page = parse_squad_html(html, team_id)
    if not stadium:
        stadium = stadium_from_page
    print(f'  {len(players_raw)} players, stadium: {stadium}')

    print('[2/5] Enriching...')
    players_raw = await enrich_players_async(players_raw, concurrency=1)
    players = []
    for p in players_raw:
        d = dict(p) if isinstance(p, dict) else vars(p)
        for old, new in {'minutes':'min','goals':'goal','assists':'assist','yellow_cards':'yellow_card','red_cards':'red_card','player_url':'profile_path'}.items():
            if old in d and new not in d: d[new] = d.pop(old)
        players.append(d)
    players = _copy_existing_last3_fields(players, existing_cache)
    enriched = sum(1 for p in players if p.get('market_value') or p.get('position'))
    print(f'  Enriched: {enriched}/{len(players)}')
    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    cache = {'team': {'id': team_id, 'name': team_name, 'slug': team_slug},
             'coach': {'name': coach_name, 'nationality': coach_nat}, 'stadium': stadium,
             'players': players, '_cached_at': time.time(), 'last_updated': time.time()}
    with open(cache_path, 'w') as f: json.dump(cache, f, indent=2, ensure_ascii=False)
    print('  [saved enrichment]')

    print('[3/5] Last 3 matches...')
    matches = await get_last3_matches_by_slug(team_id, team_name, team_slug) if team_slug else await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')
    if len(matches) < 3:
        print('ABORT: fewer than 3 matches parsed; keeping enrichment cache without wiping Last 3')
        return

    print('[4/5] Lineups + scores...')
    lineups_data_all = await fetch_and_parse_lineups(matches, known_surnames)
    valid_pairs = [(m, ld) for m, ld in zip(matches, lineups_data_all) if len(ld.get('starters', [])) > 0]
    if len(valid_pairs) < 3:
        print(f'ABORT: only {len(valid_pairs)} playable lineups from {len(matches)} candidates; keeping enrichment cache without bad Last 3')
        return
    matches = [m for m, _ in valid_pairs[:3]]
    lineups_data = [ld for _, ld in valid_pairs[:3]]
    start_counts = [len(ld.get('starters', [])) for ld in lineups_data]
    print(f'  playable START candidates: {start_counts}')

    print('[5/5] Applying...')
    players = apply_last3(players, lineups_data)
    m1s = sum(1 for p in players if p.get('last3',[])[0:1]==['START'])
    m2s = sum(1 for p in players if len(p.get('last3',[]))>1 and p['last3'][1]=='START')
    m3s = sum(1 for p in players if len(p.get('last3',[]))>2 and p['last3'][2]=='START')
    if any(c == 0 for c in [m1s, m2s, m3s]) or any(c > 11 for c in [m1s, m2s, m3s]):
        print(f'ABORT: invalid START counts={[m1s,m2s,m3s]}; keeping enrichment cache without bad Last 3')
        return
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

async def run_last3_only(team_id, team_name, team_slug=''):
    from soccerway_parser import get_last3_matches
    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
    with open(cache_path, 'r') as f: cache = json.load(f)
    players = cache['players']
    if not team_slug:
        team_slug = cache.get('team', {}).get('slug', '')
    known_surnames = set(get_surname(p['name']) for p in players if p.get('name'))

    print('[1/3] Last 3 matches...')
    matches = await get_last3_matches_by_slug(team_id, team_name, team_slug) if team_slug else await get_last3_matches(team_id, team_name)
    print(f'  {len(matches)} matches')
    if len(matches) < 3:
        print('ABORT: fewer than 3 matches parsed; keeping existing cache so Last 3 does not disappear')
        return

    print('[2/3] Lineups + scores...')
    lineups_data_all = await fetch_and_parse_lineups(matches, known_surnames)
    valid_pairs = [(m, ld) for m, ld in zip(matches, lineups_data_all) if len(ld.get('starters', [])) > 0]
    if len(valid_pairs) < 3:
        print(f'ABORT: only {len(valid_pairs)} playable lineups from {len(matches)} candidates; keeping existing cache so Last 3 does not disappear')
        return
    matches = [m for m, _ in valid_pairs[:3]]
    lineups_data = [ld for _, ld in valid_pairs[:3]]
    start_counts = [len(ld.get('starters', [])) for ld in lineups_data]
    print(f'  playable START candidates: {start_counts}')

    print('[3/3] Applying...')
    players = apply_last3(players, lineups_data)
    applied_starts = [sum(1 for p in players if len(p.get('last3', [])) > i and p['last3'][i] == 'START') for i in range(3)]
    if any(c == 0 for c in applied_starts) or any(c > 11 for c in applied_starts):
        print(f'ABORT: invalid applied START counts={applied_starts}; keeping existing cache')
        return

    cache['players'] = players
    cache['matches'] = [{'date': m.date, 'tournament': m.tournament, 'url': m.url, 'mid': m.mid,
                         'score': ld.get('score',''), 'home_team': ld.get('home_team',''), 'away_team': ld.get('away_team','')}
                        for m, ld in zip(matches, lineups_data)]
    cache['_cached_at'] = time.time()
    cache['last_updated'] = time.time()
    with open(cache_path, 'w') as f: json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f'Done! START={applied_starts}')
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
        asyncio.run(run_last3_only(team_id, team_name, team_slug))
