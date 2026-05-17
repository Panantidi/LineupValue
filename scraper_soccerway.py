#!/usr/bin/env python3
"""
Full Playwright Scraper for Soccerway
Pipeline:
1. Open squad page
2. Extract basic player data (jersey, name, age, stats)
3. Collect player profile URLs
4. Visit each player page to get position
5. Combine all data into unified JSON
"""

import json
import asyncio
from playwright.async_api import async_playwright
import time
from typing import List, Dict, Any


class SoccerwayScraper:
    """Full pipeline scraper for Soccerway squad data"""
    
    def __init__(self, headless: bool = True, concurrency: int = 3):
        self.headless = headless
        self.concurrency = concurrency
        self.browser = None
        self.base_page = None
        
    async def initialize(self):
        """Initialize browser and base page"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        self.base_page = await context.new_page()
        
    async def get_table_headers(self) -> List[str]:
        """Get table headers for stable column mapping"""
        try:
            await self.base_page.wait_for_selector('table thead th', timeout=15000)
            headers = await self.base_page.query_selector_all('table thead th')
            return [h.text_content().strip().lower() for h in headers]
        except:
            return []
    
    async def get_player_stats_headers(self) -> Dict[str, int]:
        """Get header to index mapping for player stats table"""
        headers = await self.get_table_headers()
        
        # Map common header variations to standard names
        header_map = {
            'jersey': 0,
            'no': 0,
            'number': 0,
            'name': 1,
            'player': 1,
            'age': 2,
            'games': 3,
            'apps': 3,
            'matches': 3,
            'played': 3,
            'minutes': 4,
            'min': 4,
            'minutes played': 4,
            'goals': 5,
            'g': 5,
            'assists': 6,
            'a': 6,
            'yellow': 7,
            'yc': 7,
            'yellow cards': 7,
            'red': 8,
            'rc': 8,
            'red cards': 8,
        }
        
        mapping = {}
        for i, header in enumerate(headers):
            for key, default_idx in header_map.items():
                if key in header:
                    mapping[key] = i
                    break
        
        return mapping
    
    async def extract_squad(self, url: str) -> List[Dict[str, Any]]:
        """Extract all players from squad page"""
        await self.base_page.goto(url, wait_until='networkidle', timeout=60000)
        await self.base_page.wait_for_timeout(5000)
        
        stats_headers = await self.get_player_stats_headers()
        
        # Find rows - try multiple selectors
        rows_selectors = [
            'table tbody tr',
            'tr:not(:first-child):has(td)',
        ]
        
        rows = None
        for selector in rows_selectors:
            rows = await self.base_page.query_selector_all(selector)
            if rows and len(rows) > 1:
                break
        
        if not rows or len(rows) <= 1:
            print("❌ No player rows found")
            return []
        
        players = []
        
        for row in rows:
            cells = await row.query_selector_all('td')
            if len(cells) < 9:
                continue
            
            # Get header mapping for this table
            header_map = await self.get_player_stats_headers()
            
            try:
                # Extract using header mapping if available, otherwise by index
                idx_map = header_map or {
                    'name': 1,
                    'age': 2,
                    'games': 3,
                    'minutes': 4,
                    'goals': 5,
                    'assists': 6,
                    'yellow': 7,
                    'red': 8
                }
                
                # Jersey number (first cell)
                jersey = cells[0].text_content().strip() if cells[0] else ""
                
                # Player name and link
                name_link = await row.query_selector('a[href*="/player/"]')
                name = name_link.text_content().strip() if name_link else cells[1].text_content().strip()
                
                if not name:
                    continue
                
                # Extract stats using header mapping
                age = cells[idx_map.get('age', 2)].text_content().strip() if cells[idx_map.get('age', 2)] else "-"
                games = cells[idx_map.get('games', 3)].text_content().strip() if cells[idx_map.get('games', 3)] else "-"
                minutes = cells[idx_map.get('minutes', 4)].text_content().strip() if cells[idx_map.get('minutes', 4)] else "-"
                goals = cells[idx_map.get('goals', 5)].text_content().strip() if cells[idx_map.get('goals', 5)] else "-"
                assists = cells[idx_map.get('assists', 6)].text_content().strip() if cells[idx_map.get('assists', 6)] else "-"
                yellow = cells[idx_map.get('yellow', 7)].text_content().strip() if cells[idx_map.get('yellow', 7)] else "-"
                red = cells[idx_map.get('red', 8)].text_content().strip() if cells[idx_map.get('red', 8)] else "-"
                
                # Get profile URL
                profile_url = name_link.get_attribute('href') if name_link else ""
                
                player = {
                    'jerseyNumber': jersey,
                    'name': name,
                    'age': age,
                    'gamesPlayed': games,
                    'minutesPlayed': minutes,
                    'goals': goals,
                    'assists': assists,
                    'yellowCards': yellow,
                    'redCards': red,
                    'profileUrl': profile_url,
                    'position': '',  # Will be filled in next step
                    'national': '-',  # Will need separate extraction
                }
                
                players.append(player)
                
            except Exception as e:
                print(f"❌ Error processing row: {e}")
                continue
        
        return players
    
    async def get_player_position(self, player: Dict[str, Any]) -> str:
        """Extract position from player profile page"""
        if not player.get('profileUrl'):
            return ''
        
        player_page = await self.browser.new_page()
        
        try:
            await player_page.goto(player['profileUrl'], wait_until='networkidle', timeout=60000)
            await player_page.wait_for_timeout(2000)
            
            # Extract position from page content
            position = await player_page.evaluate('''() => {
                const text = document.body.innerText.toLowerCase();
                
                if (text.includes('goalkeeper') || text.includes('goal keeper'))
                    return 'GK';
                if (text.includes('defender') || text.includes('centre-back') || text.includes('full-back'))
                    return 'DEF';
                if (text.includes('midfielder') || text.includes('central midfielder') || text.includes('winger'))
                    return 'MID';
                if (text.includes('forward') || text.includes('striker') || text.includes('centre-forward'))
                    return 'FWD';
                
                return '';
            }''')
            
            return position
            
        except Exception as e:
            print(f"⚠️ Position error for {player['name']}: {e}")
            return ''
        finally:
            await player_page.close()
    
    async def extract_positions_parallel(self, players: List[Dict[str, Any]]) -> None:
        """Extract positions for all players using async concurrency"""
        
        async def extract_single(player):
            if player.get('profileUrl'):
                player['position'] = await self.get_player_position(player)
            return player
        
        # Process with concurrency limit
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def worker(player):
            async with semaphore:
                player['position'] = await self.get_player_position(player)
                # Rate limiting
                await asyncio.sleep(1.5)
                return player
        
        tasks = [worker(p) for p in players]
        await asyncio.gather(*tasks)
    
    async def extract_nationality(self, player: Dict[str, Any]) -> str:
        """Extract nationality from player profile"""
        if not player.get('profileUrl'):
            return '-'
        
        player_page = await self.browser.new_page()
        
        try:
            await player_page.goto(player['profileUrl'], wait_until='networkidle', timeout=60000)
            await player_page.wait_for_timeout(2000)
            
            # Try to get nationality from flag or text
            nationality = await player_page.evaluate('''() => {
                // Look for flag images with alt text
                const flagImgs = document.querySelectorAll('img[alt*="Flag"]');
                if (flagImgs.length > 0 && flagImgs[0].alt) {
                    return flagImgs[0].alt.split(' ')[0]; // First word is country
                }
                
                // Look for nationality text near player name
                const nameLink = document.querySelector('.player-name a');
                if (nameLink) {
                    const parent = nameLink.parentElement;
                    const siblings = Array.from(parent.parentNode.childNodes);
                    const nameIndex = siblings.indexOf(nameLink);
                    
                    // Look for flag or nationality text in adjacent nodes
                    for (let i = nameIndex + 1; i < siblings.length; i++) {
                        const sibling = siblings[i];
                        if (sibling.nodeType === 3) { // Text node
                            const text = sibling.textContent.trim();
                            if (text.length > 0 && text.length < 50) {
                                return text;
                            }
                        }
                    }
                }
                
                return '';
            }''')
            
            return nationality if nationality else '-'
            
        except Exception as e:
            print(f"⚠️ Nationality error for {player['name']}: {e}")
            return '-'
        finally:
            await player_page.close()
    
    async def close(self):
        """Close browser and cleanup"""
        if self.base_page:
            await self.base_page.close()
        if self.browser:
            await self.browser.close()
    
    async def scrape_team(self, team_id: str, team_name: str, country: str, league: str) -> Dict[str, Any]:
        """Full pipeline: scrape team squad and combine data"""
        
        url = f"https://us.soccerway.com/team/{team_name.lower().replace(' ', '-')}/{team_id}/squad/"
        
        print(f"🎯 Scraping: {team_name}")
        print(f"📄 URL: {url}")
        
        # Step 1: Extract squad
        players = await self.extract_squad(url)
        print(f"✅ Found {len(players)} players in squad")
        
        if not players:
            return None
        
        # Step 2: Extract positions (parallel)
        print("📍 Extracting positions...")
        await self.extract_positions_parallel(players)
        
        # Step 3: Extract nationality
        print("🌍 Extracting nationality...")
        for player in players:
            player['national'] = await self.extract_nationality(player)
            await asyncio.sleep(1)  # Rate limit
        
        # Format for LineUp AI
        lineup_players = []
        for p in players:
            if not p['name']:
                continue
            
            # Map position
            pos_map = {
                'GK': 'GK',
                'DEF': 'DEF',
                'MID': 'MID',
                'FWD': 'FWD'
            }
            position = pos_map.get(p['position'], p['position'] if p['position'] else '-')
            
            lineup_player = {
                "number": p['jerseyNumber'] or "-",
                "name": p['name'],
                "national": p['national'],
                "position": position,
                "age": p['age'] if p['age'] and p['age'].isdigit() else "-",
                "apps": p['gamesPlayed'] if p['gamesPlayed'].isdigit() else "-",
                "min": p['minutesPlayed'] if p['minutesPlayed'].isdigit() else "-",
                "goal": p['goals'] if p['goals'].isdigit() else "-",
                "assist": p['assists'] if p['assists'].isdigit() else "-",
                "yellow_card": p['yellowCards'] if p['yellowCards'].isdigit() else "-",
                "red_card": p['redCards'] if p['redCards'].isdigit() else "-",
                "last5": [],
                "_last5_details": [],
                "_last5_red_details": [],
                "_last5_yellow_details": [],
                "_last5_susp_details": [],
                "_last5_loan_details": [],
                "_last5_intl_details": [],
                "profile_path": "",
                "market_value": "-"
            }
            
            lineup_players.append(lineup_player)
        
        team_data = {
            "team": {
                "id": team_id,
                "name": team_name,
                "slug": team_name.lower().replace(' ', '-'),
                "league": league,
                "country": country
            },
            "matches": [],
            "players": lineup_players
        }
        
        return team_data


async def main():
    """Main entry point"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Soccerway Full Scraper')
    parser.add_argument('--id', '-i', required=True, help='Team ID')
    parser.add_argument('--name', '-n', required=True, help='Team name')
    parser.add_argument('--country', '-c', required=True, help='Country')
    parser.add_argument('--league', '-l', required=True, help='League')
    parser.add_argument('--concurrency', '-C', type=int, default=3, help='Concurrent player page requests')
    
    args = parser.parse_args()
    
    scraper = SoccerwayScraper(headless=True, concurrency=args.concurrency)
    
    try:
        await scraper.initialize()
        
        print(f"\n{'='*60}")
        print(f"SCRAPPING: {args.name}")
        print(f"{'='*60}\n")
        
        result = await scraper.scrape_team(
            team_id=args.id,
            team_name=args.name,
            country=args.country,
            league=args.league
        )
        
        if result:
            output_file = f"/home/openclaw/.openclaw/workspace/lineup_ai_{args.country.lower()}_{args.league.replace(' ', '-').lower()}_team_{args.name.lower()}_{args.id}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Show summary
            with_stats = sum(1 for p in result['players'] if p['apps'] != "-")
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"{'='*60}")
            print(f"Team: {result['team']['name']}")
            print(f"Players: {len(result['players'])}")
            print(f"Stats available: {with_stats}/{len(result['players'])}")
            print(f"Saved to: {output_file}")
            
        else:
            print("❌ No data extracted")
            sys.exit(1)
            
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
