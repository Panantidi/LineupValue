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
    club: str = ""  # club name for national teams (stored in flag title on squad page)
    club_logo: str = ""  # club logo URL for national teams (img src in flag cell)

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
    score: str = ""
    home_team: str = ""
    away_team: str = ""
    home_score: int = 0
    away_score: int = 0
    kickoff: str = ""  # ISO datetime "2024-05-17T21:00"


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
            url = f'https://www.soccerway.com/team/{slug}/{team_id}/squad/'
        else:
            # Пробуем без slug — Soccerway может редиректнуть
            url = f'https://www.soccerway.com/team/{team_id}/squad/'

        print(f"  [Playwright] Loading {url}")

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception as e:
            # Если не загрузилось, попробуем альтернативный формат
            if team_name:
                alt_url = f'https://www.soccerway.com/team/{team_id}/squad/'
                print(f"  [Playwright] Retrying {alt_url}")
                await page.goto(alt_url, wait_until='networkidle', timeout=30000)
            else:
                raise

        # Ждём таблицу (увеличенный таймаут)
        try:
            await page.wait_for_selector('table', timeout=15000)
        except:
            # Возможно, таблица подгружается динамически — ждём ещё
            await page.wait_for_timeout(3000)
        # Scroll to trigger lazy loading of match results
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)

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
            club = ""
            club_logo = ""
            flag = player_cell.select_one('div.lineupTable__cell--flag')
            if flag:
                flag_title = flag.get('title', '') or ''
                # For national teams (World Championship): flag title = club name
                # For club teams: flag title = country name (used as national)
                national = flag_title
                club = flag_title
                # Extract club logo URL from img inside flag div
                flag_img = flag.select_one('img')
                if flag_img:
                    club_logo = flag_img.get('src', '') or ''

            def _cell_text(cls):
                cell = row.select_one(f'div.lineupTable__cell--{cls}')
                if not cell:
                    return ""
                txt = cell.text.strip()
                # Normalize Soccerway placeholders for unknown / missing values.
                # Otherwise the renderer may later call float()/int() on "?" and 500.
                if txt in {"?", "–", "—", "N/A", "n/a", "-"}:
                    return "0"
                return txt

            age = "0"
            age_cell = row.select_one('div.lineupTable__cell--age')
            if age_cell:
                age_txt = age_cell.text.strip()
                if age_txt in {"?", "–", "—", "N/A", "n/a", "-"}:
                    age = "0"
                else:
                    age = age_txt

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
                club=club,
                club_logo=club_logo,
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
            url = f'https://www.soccerway.com{player.player_url}'
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
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await context.new_page()

        if team_name:
            slug = team_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
            url = f'https://www.soccerway.com/team/{slug}/{team_id}/results/'
        else:
            url = f'https://www.soccerway.com/team/{team_id}/results/'
        print(f"  [Playwright] Loading {url}")

        await page.goto(url, wait_until='load', timeout=30000)
        await page.wait_for_timeout(3000)
        # Scroll to trigger lazy loading of match results
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)

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
        "champions-league": "CL", "europa-league": "EL", "conference-league": "ECL", "efbet-league": "EBL", "j1-league": "J1L",
        "dfb-pokal": "DFB", "copa-del-rey": "CDR", "coppa-italia": "CI",
        "league-cup": "LC", "world-championship": "WC",
    }

    # Soccerway results: each game in a div.event__match, parent div.leagues--static has league name
    game_links = soup.select('a[href*="/game/"], a[href*="/match/"]')
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
        'champions league': 'CL', 'europa league': 'EL', 'conference league': 'ECL', 'efbet league': 'EBL', 'j1 league': 'J1L',
        'dfb pokal': 'DFB', 'copa del rey': 'CDR', 'coppa italia': 'CI',
        'league cup': 'LC', 'national cup': 'CUP', 'world championship': 'WC',
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
        # Format 1: "17.05. 21:00" (DD.MM. HH:MM)
        date_match = re.search(r'(\d{1,2})\.(\d{2})\.', parent_text)
        if date_match:
            date = f"{date_match.group(1).zfill(2)}.{date_match.group(2)}"
        if not date:
            # Format 2: "May 17" (Mon DD)
            date_match = re.search(r'(\w{3})\s+(\d{1,2})', parent_text)
            if date_match:
                month = date_match.group(1)
                day = date_match.group(2).zfill(2)
                months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
                          'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
                mm = months.get(month, '')
                if mm:
                    date = f"{day}.{mm}"

        # Parse kickoff time (format: "17.05. 21:00" or "21:00")
        kickoff = ""
        time_match = re.search(r'(\d{1,2}):(\d{2})', parent_text)
        if time_match and date:
            hour, minute = time_match.group(1), time_match.group(2)
            # Assume current year
            year = datetime.now().year
            day_part, month_part = date.split('.')
            kickoff = f"{year}-{month_part}-{day_part.zfill(2)}T{hour.zfill(2)}:{minute}"

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

        match_url = f"https://www.soccerway.com{href}" if href.startswith('/') else href
        # Keep /match/ URLs — Soccerway native format

        matches.append(Match(date=date, tournament=tournament, mid=mid, url=match_url, score='', home_team='', away_team='', home_score=0, away_score=0, kickoff=kickoff))

        if len(matches) >= 3:
            break

    # Fallback: parse from div.event__match if not enough matches found
    # (new Soccerway layout may not have a[href*="/game/"] links)
    if len(matches) < 3:
        matches = []
        seen = set()
        if matches:
            print(f"  Only {len(matches)} from links, trying div.event__match fallback...")
        else:
            print("  No game links found, trying div.event__match fallback...")
        event_divs = soup.select("div.event__match--twoLine")
        if not event_divs:
            event_divs = soup.select("div.event__match")
        for ev in event_divs:
            # Get match link
            match_a = ev.find("a", href=re.compile(r"/match/"))
            if not match_a:
                match_a = ev.find("a", href=re.compile(r"/game/"))
            if not match_a:
                continue
            href = match_a.get("href", "")
            if not href:
                continue
            mid_match = re.search(r'[?&]mid=([a-zA-Z0-9]+)', href)
            mid = mid_match.group(1) if mid_match else ""
            if mid in seen:
                continue
            seen.add(mid)

            # Build URL
            match_url = f"https://www.soccerway.com{href}" if href.startswith('/') else href
            # Keep /match/ URLs — Soccerway native format

            # Get team names from participant divs
            home_div = ev.find("div", class_=re.compile(r"event__homeParticipant"))
            away_div = ev.find("div", class_=re.compile(r"event__awayParticipant"))
            time_div = ev.find("div", class_=re.compile(r"event__time"))
            home_name = home_div.text.strip().split("Advancing")[0].strip() if home_div else ""
            away_name = away_div.text.strip().split("Advancing")[0].strip() if away_div else ""
            time_text = time_div.text.strip() if time_div else ""

            # Date
            date = ""
            date_match = re.search(r"(\d{1,2})\.(\d{2})", time_text)
            if date_match:
                date = f"{date_match.group(1).zfill(2)}.{date_match.group(2)}"

            # Score from event text
            ev_text = ev.text.strip()
            our_score, opp_score = 0, 0
            after_time = ev_text.split(":")[-1] if ":" in ev_text else ev_text
            score_pat = re.search(r"(\d)(\d)([WDLT])", after_time)
            result = ""
            if score_pat:
                s1, s2 = int(score_pat.group(1)), int(score_pat.group(2))
                result = score_pat.group(3)
                if result == "W":
                    our_score, opp_score = max(s1, s2), min(s1, s2)
                elif result == "L":
                    our_score, opp_score = min(s1, s2), max(s1, s2)
                else:
                    our_score, opp_score = s1, s2

            # Tournament
            tournament = "L1"
            league_div = ev.find_parent("div", class_=re.compile(r"leagues"))
            if league_div:
                lt = league_div.text.strip().lower()
                for key, val in league_map.items():
                    if key in lt:
                        tournament = val
                        break

            # Home/away
            home_s, away_s = 0, 0
            tn = team_name.lower().replace(" ", "")
            hn = home_name.lower().replace(" ", "")
            if tn in hn or hn in tn:
                home_s, away_s = our_score, opp_score
            else:
                home_s, away_s = opp_score, our_score

            score_str = f"{home_name} {home_s}-{away_s} {away_name}" if home_name and away_name else ""

            matches.append(Match(date=date, tournament=tournament, mid=mid, url=match_url,
                                score=score_str, home_team=home_name, away_team=away_name,
                                home_score=home_s, away_score=away_s))
            print(f"    {date} {tournament}: {score_str}")
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
            
            # Extract slug from URL (works for both /game/ and /match/)
            game_path = re.search(r'/game/([^?]+)', match.url)
            match_path = re.search(r'/match/([^?]+)', match.url)
            slug = game_path.group(1).rstrip('/') if game_path else (match_path.group(1).rstrip('/') if match_path else "")
            
            if slug and mid:
                url = f'https://www.soccerway.com/match/{slug}/summary/lineups/?mid={mid}'
            else:
                url = match.url

            try:
                print(f"    Loading lineups: {match.date} {match.tournament}")
                await page.goto(url, wait_until='load', timeout=15000)
                await page.wait_for_timeout(2000)
                # Scroll to load lazy content
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await page.wait_for_timeout(300)
                await page.wait_for_timeout(1000)
                html = await page.content()
            except Exception as e:
                print(f"    Error loading lineups for {match.date}: {e}")
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': [], 'missing': [], 'captains': [], 'score': '', 'home_team': '', 'away_team': ''})
                continue

            soup = BeautifulSoup(html, 'html.parser')
            starters = []
            substitutes = []

            # NEW Soccerway HTML structure (June 2026):
            # - lf__formation = HOME team (first formation without lf__formationAway class)
            # - lf__formation lf__formationAway = AWAY team
            # - lf__player contains individual player info
            # - wcl-lineupsParticipantName_* contains player name
            
            # Find formations
            home_formation = soup.find('div', class_='lf__formation')
            # Check if it has lf__formationAway class (if so, find the other one)
            if home_formation and 'lf__formationAway' in home_formation.get('class', []):
                # This is actually AWAY, find HOME
                formations = soup.find_all('div', class_='lf__formation')
                for f in formations:
                    if 'lf__formationAway' not in f.get('class', []):
                        home_formation = f
                        break
            
            away_formation = soup.find('div', class_='lf__formationAway')
            
            # Extract players from formations
            def extract_players_from_formation(formation):
                players = []
                if formation:
                    for pdiv in formation.find_all('div', class_='lf__player'):
                        name_el = pdiv.find('div', attrs={'data-testid': re.compile(r'wcl-lineupsParticipantName')})
                        if name_el:
                            raw_name = name_el.get_text().strip()
                            name = re.sub(r'^\d+', '', raw_name).strip()
                            if name and len(name) > 1:
                                players.append(name)
                return players
            
            home_players = extract_players_from_formation(home_formation)
            away_players = extract_players_from_formation(away_formation)
            
            if not home_players and not away_players:
                print(f"    {match.date}: No players found in formations")
                results.append({'date': match.date, 'tournament': match.tournament, 'starters': [], 'substitutes': []})
                continue

            # Determine HOME/AWAY from page title
            title_el = soup.find('title')
            is_home = True  # default
            
            if title_el:
                title_text = title_el.get_text()
                # Parse: "Team1 v Team2 date, Lineups - Soccerway.com"
                names_match = re.search(r'\|\s*([^v]+)\s+v\s+', title_text)
                if names_match:
                    home_team_in_title = names_match.group(1).strip().lower()
                    team_name_lower = team_name.lower()
                    if team_name_lower in home_team_in_title or home_team_in_title in team_name_lower:
                        is_home = True
                    else:
                        is_home = False

            # Get starters from the correct formation
            starters = home_players if is_home else away_players
            substitutes = []  # TODO: extract from substitutes section

            # Parse Captains from player divs
            captains = set()
            for pdiv in soup.find_all('div', class_='lf__player'):
                if '(C)' in pdiv.get_text():
                    name_el = pdiv.find('div', attrs={'data-testid': re.compile(r'wcl-lineupsParticipantName')})
                    if name_el:
                        raw_name = name_el.get_text().strip()
                        name = re.sub(r'^\d+', '', raw_name).strip()
                        if name:
                            captains.add(name.split()[0].lower())

            # Parse Missing Players section
            missing_players = []
            # Look for text containing "Missing Players" and find parent section
            for pdiv in soup.find_all('div', class_='lf__player'):
                text = pdiv.get_text()
                # Check if this is in a missing players section
                parent = pdiv.find_parent('div', class_='lf__lineUp')
                if parent and 'missing' in parent.get_text().lower():
                    name_el = pdiv.find('div', attrs={'data-testid': re.compile(r'wcl-lineupsParticipantName')})
                    if name_el:
                        raw_name = name_el.get_text().strip()
                        name = re.sub(r'^\d+', '', raw_name).strip()
                        if name:
                            # Try to find reason
                            reason = ''
                            all_text = pdiv.get_text()
                            if 'injury' in all_text.lower():
                                reason = 'Injury'
                            elif 'suspension' in all_text.lower():
                                reason = 'Suspension'
                            missing_players.append({'name': name, 'reason': reason})

            # Parse score from page title
            title_el = soup.find('title')
            title_text = title_el.get_text() if title_el else ''
            score_str = ''
            home_team_name = ''
            away_team_name = ''
            score_match = re.search(r'(\w+)\s+(\d+)\s*-\s*(\d+)\s+(\w+)\s*\|', title_text)
            if score_match:
                abbr1, s1, s2, abbr2 = score_match.group(1), int(score_match.group(2)), int(score_match.group(3)), score_match.group(4)
                names_match = re.search(r'\|\s*([^v]+)\s+v\s+([^\d]+)', title_text)
                if names_match:
                    home_team_name = names_match.group(1).strip()
                    away_team_name = names_match.group(2).strip().split(',')[0].strip()
                    score_str = f'{home_team_name} {s1}-{s2} {away_team_name}'
                else:
                    score_str = f'{abbr1} {s1}-{s2} {abbr2}'

            print(f"    {match.date} ({side_label}): starters={len(starters)}, subs={len(substitutes)}, missing={len(missing_players)}, captains={len(captains)}")
            results.append({
                'date': match.date,
                'tournament': match.tournament,
                'starters': starters,
                'substitutes': substitutes,
                'missing': missing_players,
                'captains': list(captains),
                'score': score_str,
                'home_team': home_team_name,
                'away_team': away_team_name
            })

        await browser.close()

    return results


# ============================================================
# Step 5: Merge everything - build Last 3 per player
# ============================================================

def apply_last3_to_players(players: List[Player], lineups_data: List[Dict]) -> List[Player]:
    """For each player, determine start/sub/missing status for each of 3 matches.

    Each Soccerway lineup entry is assigned to at most one roster player. This
    prevents duplicate green START circles when two players share the same
    surname (or first displayed token), e.g. Murphy A. / Murphy J.
    """

    def get_surname(name: str) -> str:
        return name.split()[0].lower().replace('.', '').strip() if name and name.strip() else ""

    def name_initials(name: str) -> List[str]:
        cleaned = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ\s.-]', ' ', str(name or '')).replace('.', ' ')
        return [p[0].lower() for p in cleaned.split() if p and p[0].isalpha()]

    def match_lineup_to_player(lineup_name: str, candidates: List[Player]):
        l_surname = get_surname(lineup_name)
        same = [p for p in candidates if get_surname(p.name) == l_surname]
        if not same:
            return None
        if len(same) == 1:
            return same[0]
        parts = str(lineup_name or '').replace('.', ' ').split()
        l_extra = name_initials(' '.join(parts[1:])) if len(parts) > 1 else []
        if l_extra:
            filtered = []
            for p in same:
                p_parts = str(p.name or '').split()
                p_extra = name_initials(' '.join(p_parts[1:])) if len(p_parts) > 1 else []
                if all(i in p_extra for i in l_extra):
                    filtered.append(p)
            if len(filtered) == 1:
                return filtered[0]
            if filtered:
                same = filtered
        def mins(player):
            try:
                return int(str(player.minutes or 0).replace(',', ''))
            except Exception:
                return 0
        return sorted(same, key=mins, reverse=True)[0]

    def assign(lineup_names: List[str], candidates: List[Player]):
        available = list(candidates)
        out = {}
        for lname in lineup_names or []:
            player = match_lineup_to_player(lname, available)
            if not player:
                continue
            out[id(player)] = player
            available.remove(player)
        return out

    for player in players:
        player.last3 = []
        player.last3_missing = []
        player.last3_captain = []

    for match_idx, match_data in enumerate(lineups_data):
        starter_map = assign(match_data.get('starters', []), players)
        sub_map = assign(
            match_data.get('substitutes', []),
            [p for p in players if id(p) not in starter_map]
        )
        missing_list = match_data.get('missing', []) or []
        missing_names = [m.get('name', '') for m in missing_list if isinstance(m, dict)]
        missing_map = assign(
            missing_names,
            [p for p in players if id(p) not in starter_map and id(p) not in sub_map]
        )
        missing_reason = {}
        for m in missing_list:
            if not isinstance(m, dict):
                continue
            mp = match_lineup_to_player(m.get('name', ''), [p for p in players if id(p) in missing_map])
            if mp:
                missing_reason[id(mp)] = m.get('reason', '')

        captains = match_data.get('captains_full', match_data.get('captains', []))
        captain_ids = set()
        for cap in captains:
            cp = match_lineup_to_player(cap, [p for p in players if id(p) in starter_map])
            if cp:
                captain_ids.add(id(cp))

        for player in players:
            key = id(player)
            if key in starter_map:
                player.last3.append("START")
                player.last3_missing.append(None)
                player.last3_captain.append(key in captain_ids)
            elif key in sub_map:
                player.last3.append("SUB")
                player.last3_missing.append(None)
                player.last3_captain.append(False)
            elif key in missing_map:
                player.last3.append("")
                player.last3_missing.append(missing_reason.get(key, ""))
                player.last3_captain.append(False)
            else:
                player.last3.append("—")
                player.last3_missing.append(None)
                player.last3_captain.append(False)

    for player in players:
        while len(player.last3) < 3:
            player.last3.append("—")
            player.last3_missing.append(None)
            player.last3_captain.append(False)
        player.last3 = player.last3[:3]
        player.last3_missing = player.last3_missing[:3]
        player.last3_captain = player.last3_captain[:3]

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
            "club": p.club,
            "club_logo": p.club_logo,
            "market_value": p.market_value,
            "last3": p.last3[:3] if p.last3 else ["—", "—", "—"],
            "last3_missing": p.last3_missing[:3] if hasattr(p, 'last3_missing') and p.last3_missing else [None, None, None],
            "last3_captain": p.last3_captain[:3] if hasattr(p, 'last3_captain') and p.last3_captain else [False, False, False],
        })

    matches_out = []
    for m in team_data.last3_matches:
        matches_out.append({
            "date": m.date,
            "tournament": m.tournament,
            "url": m.url,
            "mid": m.mid,
            "score": m.score,
            "home_team": m.home_team,
            "away_team": m.away_team,
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
    import asyncio
    
    # Wrap entire fetch in timeout
    async def _fetch():
        # Check cache (skip if force_refresh)
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
    
    try:
        return await asyncio.wait_for(_fetch(), timeout=180)
    except asyncio.TimeoutError:
        print(f"  [fetch_team_data] Timeout after 180s for {team_id}")
        raise
    except Exception as e:
        print(f"  [fetch_team_data] Error: {e}")
        raise


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