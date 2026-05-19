#!/usr/bin/env python3
"""
Soccerway Team Parser for x11radar.ru
Usage: python soccerway_parser.py --team "strasbourg" --team_id "nP6UzIU1"
"""

import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import hashlib


# ============================================================
# Data models
# ============================================================

@dataclass
class Player:
    number: str
    name: str
    age: str
    apps: str
    minutes: str
    goals: str
    assists: str
    yellow_cards: str
    red_cards: str
    position: str = ""
    market_value: str = ""
    player_url: str = ""
    last3: List[str] = None  # ["START", "SUB", "—"] for 3 matches
    national: str = ""

    def __post_init__(self):
        if self.last3 is None:
            self.last3 = []


@dataclass
class Match:
    date: str  # "11.05"
    tournament: str  # "PL"
    mid: str  # match id for lineups URL
    url: str = ""
    opponent: str = ""


@dataclass
class TeamData:
    team_name: str
    team_id: str
    coach: str
    stadium: str
    players: List[Player]
    last3_matches: List[Match]
    updated_at: str


# ============================================================
# Cache
# ============================================================

CACHE_DIR = "/home/openclaw/.openclaw/workspace/cache"
CACHE_TTL_HOURS = 6

def get_cache_path(team_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{team_id}.json")

def load_from_cache(team_id: str) -> Optional[TeamData]:
    cache_path = get_cache_path(team_id)
    if not os.path.exists(cache_path):
        return None

    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated_at = datetime.fromisoformat(data['updated_at'])
    if datetime.now() - updated_at > timedelta(hours=CACHE_TTL_HOURS):
        return None

    players = [Player(**p) for p in data['players']]
    matches = [Match(**m) for m in data['last3_matches']]

    return TeamData(
        team_name=data['team_name'],
        team_id=data['team_id'],
        coach=data['coach'],
        stadium=data['stadium'],
        players=players,
        last3_matches=matches,
        updated_at=data['updated_at']
    )

def save_to_cache(team_data: TeamData):
    cache_path = get_cache_path(team_data.team_id)
    data = {
        'team_name': team_data.team_name,
        'team_id': team_data.team_id,
        'coach': team_data.coach,
        'stadium': team_data.stadium,
        'players': [asdict(p) for p in team_data.players],
        'last3_matches': [asdict(m) for m in team_data.last3_matches],
        'updated_at': datetime.now().isoformat()
    }
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# Step 1: Parse squad page (using Playwright)
# ============================================================

async def get_squad_page(team_id: str, team_name: str = "") -> str:
    """Fetch squad page HTML using Playwright headless"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'
        )
        # Анти-детекция headless
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        # Soccerway URL: /team/{slug}/{id}/squad/
        # Если есть имя команды — формируем slug, иначе используем только ID
        if team_name:
            slug = team_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
            url = f'https://us.soccerway.com/team/{slug}/{team_id}/squad/'
        else:
            # Пробуем без slug — Soccerway может редиректнуть
            url = f'https://us.soccerway.com/team/{team_id}/squad/'

        print(f"  [Playwright] Loading {url}")

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception as e:
            # Если не загрузилось, попробуем альтернативный формат
            if team_name:
                alt_url = f'https://us.soccerway.com/team/{team_id}/squad/'
                print(f"  [Playwright] Retrying {alt_url}")
                await page.goto(alt_url, wait_until='networkidle', timeout=30000)
            else:
                raise

        # Ждём таблицу (увеличенный таймаут)
        try:
            await page.wait_for_selector('table', timeout=15000)
        except:
            # Возможно, таблица подгружается динамически — ждём ещё
            await page.wait_for_timeout(5000)

        html = await page.content()
        await browser.close()
        return html


def parse_squad_html(html: str, team_id: str) -> Tuple[List[Player], str, str]:
    """Parse players, coach, stadium from squad page HTML"""
    soup = BeautifulSoup(html, 'html.parser')

    # Extract coach
    coach = ""
    # Coach: //*[@id="overall-all-table"]/div[5]/div[3]/div[1]/div[2]/a
    coach_link = soup.select_one('#overall-all-table a[href*="/coach/"], #overall-all-table a[href*="/manager/"]')
    if not coach_link:
        # Альтернативный поиск: последний блок в overall-all-table, div[3] → первый div → второй div → a
        overall = soup.select_one('#overall-all-table')
        if overall:
            coach_link = overall.select_one('div:nth-of-type(5) > div:nth-child(3) > div:first-child > div:nth-child(2) > a')
    if not coach_link:
        # Поиск по контексту — <div>Coach</div>
        coach_label = soup.find(string=re.compile(r'^Coach$', re.I))
        if coach_label:
            parent = coach_label.find_parent()
            if parent:
                a = parent.find_next('a')
                if a:
                    coach_link = a
    if coach_link:
        coach = coach_link.text.strip()

    # Stadium
    stadium = ""
    # Ищем span с текстом "Stadium:" и берём tail текст родителя
    stadium_span = soup.find('span', string=re.compile(r'Stadium', re.I))
    if not stadium_span:
        stadium_span = soup.find('span', class_=re.compile(r'heading__info--key|.*key.*', re.I), string=re.compile(r'Stadium', re.I))
    if stadium_span:
        # Tail текст после span (само название стадиона)
        tail = stadium_span.next_sibling
        if tail and isinstance(tail, str) and tail.strip():
            stadium = tail.strip()
        else:
            # Попробуем следующий span
            nxt = stadium_span.find_next_sibling('span')
            if nxt:
                # Это может быть "(City)" — пропустим
                pass
            # Или текст внутри родителя после span
            parent_text = stadium_span.parent.get_text()
            stadium = parent_text.replace(stadium_span.text, '').strip()
            # Убираем (City) если есть
            stadium = re.sub(r'\([^)]*\)', '', stadium).strip()

    # ---- Парсинг состава через div.lineupTable ----
    # Soccerway: Total = overall-all-table (34 игрока + Coach)
    # Берём ТОЛЬКО Total — без суммирования по турнирам
    players = []

    all_tables = soup.select('div.lineupTable--soccer')

    for table in all_tables:
        parent_id = table.parent.get('id', '') if table.parent else ''
        if parent_id != 'overall-all-table':
            continue

        title_elem = table.select_one('div.lineupTable__title')
        if title_elem:
            pos_group = title_elem.text.strip()
            if pos_group.lower() in ('coach', 'manager', 'trainer'):
                continue

        for row in table.select('div.lineupTable__row'):
            player_cell = row.select_one('div.lineupTable__cell--player')
            if not player_cell:
                continue
            link = player_cell.select_one('a[href*="/player/"]')
            name = link.text.strip() if link else player_cell.text.strip()
            if not name:
                continue

            number = ""
            jersey = row.select_one('div.lineupTable__cell--jersey')
            if jersey:
                number = jersey.text.strip()

            player_url = link.get('href', '') if link else ""

            national = ""
            flag = player_cell.select_one('div.lineupTable__cell--flag')
            if flag:
                national = flag.get('title', '') or ''

            age = ""
            age_cell = row.select_one('div.lineupTable__cell--age')
            if age_cell:
                age = age_cell.text.strip()

            def _cell_text(cls):
                cell = row.select_one(f'div.lineupTable__cell--{cls}')
                return cell.text.strip() if cell else ""

            apps = _cell_text('matchesPlayed')
            minutes = _cell_text('minutesPlayed')
            goals = _cell_text('goal')
            assists = _cell_text('assist')
            yellow = _cell_text('yellowCard')
            red = _cell_text('redCard')

            players.append(Player(
                number=number,
                name=name,
                age=age,
                apps=apps,
                minutes=minutes,
                goals=goals,
                assists=assists,
                yellow_cards=yellow,
                red_cards=red,
                player_url=player_url,
                national=national,
            ))

    print(f"    Players from Total (overall-all-table): {len(players)}")

    # Deduplicate by name (Soccerway sometimes shows duplicates)
    seen_names = set()
    unique_players = []
    for p in players:
        if p.name not in seen_names:
            seen_names.add(p.name)
            unique_players.append(p)
    if len(unique_players) < len(players):
        print(f"    Deduplicated: {len(players)} -> {len(unique_players)}")
        players = unique_players

    # Fallback: если новый формат не найден, пробуем старый (table)
    if not players:
        player_links = soup.select('table tbody tr td a[href*="/player/"]')
        for link in player_links:
            name = link.text.strip()
            if not name:
                continue
            player_url = link.get('href', '')
            row = link.find_parent('tr')
            if not row:
                continue
            cells = row.find_all('td')
            if len(cells) < 6:
                continue
            number = cells[0].text.strip() if cells else ""
            age = ""
            for cell in cells:
                txt = cell.text.strip()
                if txt.isdigit() and 14 < int(txt) < 50:
                    age = txt
                    break
            numeric_cells = [c for c in cells if c.text.strip().replace('-', '').isdigit()]
            apps = numeric_cells[0].text.strip() if len(numeric_cells) > 0 else ""
            minutes = numeric_cells[1].text.strip() if len(numeric_cells) > 1 else ""
            goals = numeric_cells[2].text.strip() if len(numeric_cells) > 2 else ""
            assists = numeric_cells[3].text.strip() if len(numeric_cells) > 3 else ""
            yellow = numeric_cells[4].text.strip() if len(numeric_cells) > 4 else ""
            red = numeric_cells[5].text.strip() if len(numeric_cells) > 5 else ""
            players.append(Player(
                number=number, name=name, age=age, apps=apps,
                minutes=minutes, goals=goals, assists=assists,
                yellow_cards=yellow, red_cards=red, player_url=player_url,
            ))

    return players, coach, stadium


# ============================================================
# Step 2: Get Pos and MV from player page (parallel)
# ============================================================

async def enrich_players_async(players: List[Player], concurrency: int = 1) -> List[Player]:
    """Enrich players with position and market value using ONE Playwright browser"""
    print(f"  Enriching {len(players)} players (sequential, 1 browser)...")

    pos_map = {
        'Goalkeeper': 'GK', 'Defender': 'DF', 'Midfielder': 'MF', 'Forward': 'FW',
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        for player in players:
            if not player.player_url:
                continue
            url = f'https://us.soccerway.com{player.player_url}'
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                await page.wait_for_timeout(1000)
                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')

                # Position
                pos_div = soup.select_one('div.playerTeam')
                if pos_div:
                    raw_pos = pos_div.text.strip().split()[0]
                    player.position = pos_map.get(raw_pos, raw_pos)
                else:
                    header = soup.select_one('[class*=playerHeader]')
                    if header:
                        bold = header.select_one('span[class*=wcl-bold]')
                        if bold:
                            raw_pos = bold.text.strip()
                            player.position = pos_map.get(raw_pos, raw_pos)

                # Market Value
                mv_span = soup.find('span', string=re.compile(r'€[\d,.]+[mMkK]'))
                if mv_span:
                    player.market_value = mv_span.text.strip()

                if player.position or player.market_value:
                    print(f"    + {player.name} -> {player.position} / {player.market_value}")
            except Exception as e:
                print(f"    err {player.name}: {e}")

        await browser.close()

    return players


# ============================================================
# Step 3: Get last 3 matches from results page
# ============================================================

async def get_last3_matches(team_id: str, team_name: str = "") -> List[Match]:
    """Fetch last 3 completed matches from results page"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        if team_name:
            slug = team_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
            url = f'https://us.soccerway.com/team/{slug}/{team_id}/results/'
        else:
            url = f'https://us.soccerway.com/team/{team_id}/results/'
        print(f"  [Playwright] Loading {url}")

        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(5000)

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    matches = []

    # Comp abbreviation map
    comp_map = {
        "ligue-1": "L1", "ligue-2": "L2", "premier-league": "PL",
        "championship": "CH", "la-liga": "LL", "laliga": "LL",
        "serie-a": "SA", "bundesliga": "BL", "bundesliga-2": "B2",
        "eredivisie": "ER", "liga-portugal": "LP", "jupiler-pro-league": "JPL",
        "super-lig": "SL", "super-league": "SUL", "superliga": "SUP",
        "allsvenskan": "ALL", "eliteserien": "ELI",
        "fa-cup": "FA", "coupe-de-france": "CDF",
        "champions-league": "CL", "europa-league": "EL", "conference-league": "ECL",
        "dfb-pokal": "DFB", "copa-del-rey": "CDR", "coppa-italia": "CI",
        "league-cup": "LC",
    }

    # Soccerway results: each game in a div.event__match, parent div.leagues--static has league name
    game_links = soup.select('a[href*="/game/"]')
    seen = set()
    current_league = ""

    # League abbreviation map
    league_map = {
        'ligue 1': 'L1', 'ligue 2': 'L2', 'premier league': 'PL',
        'championship': 'CH', 'la liga': 'LL', 'laliga': 'LL',
        'serie a': 'SA', 'bundesliga': 'BL', '2. bundesliga': 'B2',
        'eredivisie': 'ER', 'liga portugal': 'LP', 'jupiler pro league': 'JPL',
        'super lig': 'SL', 'super league': 'SUL', 'superliga': 'SUP',
        'allsvenskan': 'ALL', 'eliteserien': 'ELI',
        'fa cup': 'FA', 'coupe de france': 'CDF',
        'champions league': 'CL', 'europa league': 'EL', 'conference league': 'ECL',
        'dfb pokal': 'DFB', 'copa del rey': 'CDR', 'coppa italia': 'CI',
        'league cup': 'LC', 'national cup': 'CUP',
    }

    for link in game_links:
        href = link.get('href', '')
        if not href:
            continue

        # Extract mid
        mid_match = re.search(r'[?&]mid=([a-zA-Z0-9]+)', href)
        mid = mid_match.group(1) if mid_match else ""
        if mid in seen:
            continue
        seen.add(mid)

        # Date from parent div text: "May 17 09:00 PMStrasbourgMonaco54W"
        parent = link.find_parent('div', class_=re.compile(r'event__match'))
        parent_text = parent.text.strip() if parent else ""

        date = ""
        date_match = re.search(r'(\w{3})\s+(\d{1,2})', parent_text)
        if date_match:
            month = date_match.group(1)
            day = date_match.group(2).zfill(2)
            months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
                      'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            mm = months.get(month, '')
            if mm:
                date = f"{day}.{mm}"

        # Tournament from parent league container
        tournament = ""
        league_div = link.find_parent('div', class_=re.compile(r'leagues'))
        if league_div:
            league_text = league_div.text.strip().split('\n')[0].strip()
            # "Ligue 1" or "National Cup" etc
            for key, val in league_map.items():
                if key in league_text.lower():
                    tournament = val
                    break
        if not tournament:
            tournament = "CUP"

        match_url = f"https://us.soccerway.com{href}" if href.startswith('/') else href

        matches.append(Match(date=date, tournament=tournament, mid=mid, url=match_url))

        if len(matches) >= 3:
            break

    return matches


# ============================================================
# Step 4: Get lineups for a match
# ============================================================

async def fetch_all_lineups(matches: List[Match], team_name: str) -> List[Dict]:
    """Fetch lineups for all 3 matches using ONE browser"""
    print(f"  Fetching lineups for {len(matches)} matches...")

    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()

        for match in matches:
            if not match.url:
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': []})
                continue

            # Build lineups URL from match URL
            # match.url = https://us.soccerway.com/game/monaco-2PIvr8o4/strasbourg-nP6UzIU1/?mid=44Vsqc0E
            # lineups URL = .../summary/lineups/?mid=...
            mid = match.mid or ""
            if not mid:
                mid_match = re.search(r'mid=([a-zA-Z0-9]+)', match.url)
                mid = mid_match.group(1) if mid_match else ""
            
            # Extract game slug from URL
            game_path = re.search(r'/game/([^?]+)', match.url)
            slug = game_path.group(1) if game_path else ""
            
            if slug and mid:
                url = f'https://us.soccerway.com/game/{slug}/summary/lineups/?mid={mid}'
            else:
                url = match.url

            try:
                print(f"    Loading lineups: {match.date} {match.tournament}")
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await page.wait_for_timeout(4000)
                html = await page.content()
            except Exception as e:
                print(f"    Error loading lineups for {match.date}: {e}")
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': []})
                continue

            soup = BeautifulSoup(html, 'html.parser')
            starters = []
            substitutes = []

            # Parse lineups page:
            # Starting Lineups and Substitutes sections with lf__side (home/reversed=away)
            # Players in a[href*="/player/"] inside div.lf__participantNew parents
            # lf__isReversed class = away team

            # Determine if our team is home or away from the URL slug
            # URL: /game/{away_slug}/{home_slug}/... — but actually order varies
            # Better: check team_name against page content
            is_reversed = None  # True=away, False=home

            # Find team names in the page
            team_links = soup.select('a[href*="/team/"]')
            for tl in team_links:
                if team_name.lower() in tl.text.lower():
                    # Check if this team is in a reversed container
                    for parent in [tl] + list(tl.parents)[:8]:
                        cls = ' '.join(parent.get('class', []))
                        if 'lf__isReversed' in cls:
                            is_reversed = True
                            break
                        if 'lf__side' in cls and 'lf__isReversed' not in cls:
                            is_reversed = False
                            break
                    break

            if is_reversed is None:
                # Fallback: try URL slug comparison
                if slug:
                    parts = slug.split('/')
                    if len(parts) >= 2:
                        # If team_name matches first part -> away (reversed=True)
                        if team_name.lower() in parts[0].lower():
                            is_reversed = True
                        else:
                            is_reversed = False

            # Parse Starting Lineups section
            start_span = soup.find('span', string=re.compile(r'Starting Lineups', re.I))
            if start_span:
                start_sec = start_span.find_parent('div', class_='section')
                if start_sec:
                    # Players are in span[class*=wcl-name_] (not <a> links)
                    name_spans = start_sec.select('span[class*="wcl-name_"]')
                    for ns in name_spans:
                        name = ns.text.strip()
                        if not name:
                            continue
                        player_reversed = False
                        for parent in [ns] + list(ns.parents)[:10]:
                            cls = ' '.join(parent.get('class', []))
                            if 'lf__isReversed' in cls:
                                player_reversed = True
                                break
                        if player_reversed == is_reversed:
                            starters.append(name)

            # Parse Substitutes section
            sub_span = soup.find('span', string=re.compile(r'^Substitutes$', re.I))
            if sub_span:
                sub_sec = sub_span.find_parent('div', class_='section')
                if sub_sec:
                    name_spans = sub_sec.select('span[class*="wcl-name_"]')
                    for ns in name_spans:
                        name = ns.text.strip()
                        if not name:
                            continue
                        player_reversed = False
                        for parent in [ns] + list(ns.parents)[:10]:
                            cls = ' '.join(parent.get('class', []))
                            if 'lf__isReversed' in cls:
                                player_reversed = True
                                break
                        if player_reversed == is_reversed:
                            substitutes.append(name)

            print(f"    {match.date}: starters={len(starters)}, subs={len(substitutes)}")
            results.append({
                'date': match.date,
                'tournament': match.tournament,
                'starters': starters,
                'substitutes': substitutes
            })

        await browser.close()

    return results


# ============================================================
# Step 5: Merge everything - build Last 3 per player
# ============================================================

def apply_last3_to_players(players: List[Player], lineups_data: List[Dict]) -> List[Player]:
    """For each player, determine start/sub status for each of 3 matches"""

    def normalize(name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    for match_idx, match_data in enumerate(lineups_data):
        starters_norm = {normalize(p) for p in match_data['starters']}
        subs_norm = {normalize(p) for p in match_data['substitutes']}

        for player in players:
            player_norm = normalize(player.name)

            # Also try last name only (Soccerway may have different name format)
            player_last = player_norm.split()[-1] if player_norm else ""

            found = False
            if player_norm in starters_norm or any(player_norm in s for s in starters_norm):
                player.last3.append("START")
                found = True
            elif player_last and any(player_last in s for s in starters_norm):
                player.last3.append("START")
                found = True
            elif player_norm in subs_norm or any(player_norm in s for s in subs_norm):
                player.last3.append("SUB")
                found = True
            elif player_last and any(player_last in s for s in subs_norm):
                player.last3.append("SUB")
                found = True

            if not found:
                player.last3.append("—")

    return players


# ============================================================
# Convert to Player_Info.json format (compatible with lineup_team_view.py)
# ============================================================

def to_lineup_format(team_data: TeamData) -> dict:
    """Convert TeamData to the format expected by lineup_team_view.py"""
    players_out = []
    for p in team_data.players:
        players_out.append({
            "number": p.number,
            "name": p.name,
            "national": p.national,
            "position": p.position,
            "age": p.age,
            "apps": p.apps,
            "min": p.minutes,
            "goal": p.goals,
            "assist": p.assists,
            "yellow_card": p.yellow_cards,
            "red_card": p.red_cards,
            "profile_path": p.player_url,
            "market_value": p.market_value,
            "last3": p.last3[:3] if p.last3 else ["—", "—", "—"],
        })

    matches_out = []
    for m in team_data.last3_matches:
        matches_out.append({
            "date": m.date,
            "comp": m.tournament,
            "url": m.url,
        })

    return {
        "team": {
            "id": team_data.team_id,
            "name": team_data.team_name,
            "slug": team_data.team_name.lower().replace(" ", "-"),
        },
        "coach": {"name": team_data.coach, "nationality": ""},
        "stadium": team_data.stadium,
        "matches": matches_out,
        "players": players_out,
        "last_updated": team_data.updated_at,
    }


# ============================================================
# Main orchestration
# ============================================================

async def fetch_team_data(team_id: str, team_name: str = "", force_refresh: bool = False) -> TeamData:
    """Main function: fetch complete team data with caching"""
    # Check cache
    if not force_refresh:
        cached = load_from_cache(team_id)
        if cached:
            print(f"  Using cached data for {team_name or team_id}")
            return cached

    print(f"  Fetching fresh data for {team_name or team_id}...")

    # Step 1: Get squad page
    print("  Step 1/4: Parsing squad page...")
    squad_html = await get_squad_page(team_id, team_name)
    players, coach, stadium = parse_squad_html(squad_html, team_id)
    print(f"    Found {len(players)} players, Coach: {coach}")

    # Step 2: Enrich with Pos and MV (async Playwright)
    print("  Step 2/4: Enriching player details (Pos, MV)...")
    players = await enrich_players_async(players, concurrency=3)

    # Step 3: Get last 3 matches
    print("  Step 3/4: Fetching last 3 matches...")
    last3_matches = await get_last3_matches(team_id, team_name)
    print(f"    Matches: {[(m.date, m.tournament) for m in last3_matches]}")

    # Step 4: Get lineups for each match (parallel async)
    print("  Step 4/4: Fetching lineups...")
    lineups_data = await fetch_all_lineups(last3_matches, team_name)

    # Step 5: Apply Last 3 to players
    players = apply_last3_to_players(players, lineups_data)

    # Create result
    result = TeamData(
        team_name=team_name,
        team_id=team_id,
        coach=coach,
        stadium=stadium,
        players=players,
        last3_matches=last3_matches,
        updated_at=datetime.now().isoformat()
    )

    # Save to cache
    save_to_cache(result)
    print(f"  Data saved to cache (TTL: {CACHE_TTL_HOURS}h)")

    return result


# ============================================================
# CLI entry point
# ============================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Soccerway Team Parser')
    parser.add_argument('--team', required=True, help='Team name (e.g., strasbourg)')
    parser.add_argument('--team_id', required=True, help='Soccerway team ID (e.g., nP6UzIU1)')
    parser.add_argument('--force', action='store_true', help='Force refresh')

    args = parser.parse_args()

    data = await fetch_team_data(args.team_id, args.team, force_refresh=args.force)

    # Save in Player_Info.json format
    output = to_lineup_format(data)
    output_file = f"{args.team_id}_data.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  JSON saved to {output_file}")
    print(f"  Players: {len(output['players'])}")
    print(f"  Matches: {len(output['matches'])}")


if __name__ == '__main__':
    asyncio.run(main())
