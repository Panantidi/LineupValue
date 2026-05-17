#!/usr/bin/env python3
"""
Smart scraper:
1. Load your existing JSON (with players, positions, jersey numbers)
2. Extract player profile URLs from squad page
3. For each player, visit profile page to get position (if not already known)
4. Get stats from squad page if available
5. Combine all data
"""

import json
import re
from playwright.async_api import async_playwright
import asyncio


class SmartScraper:
    """Smart scraper using existing data + profile page extraction"""
    
    def __init__(self, concurrency: int = 3):
        self.concurrency = concurrency
        self.browser = None
        self.base_page = None
    
    async def initialize(self):
        """Initialize browser"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        self.base_page = await context.new_page()
    
    async def extract_player_links_from_squad(self, url: str) -> list:
        """Extract player name -> URL mapping from squad page"""
        await self.base_page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await self.base_page.wait_for_timeout(8000)
        
        # Get all player links
        links = await self.base_page.query_selector_all('a[href*="/player/"]')
        
        player_map = {}
        for link in links:
            name_raw = await link.text_content()
            name = name_raw.strip() if name_raw else ""
            href = await link.get_attribute('href')
            if href and not href.startswith('http'):
                href = 'https://us.soccerway.com' + href
            
            if name and href and name not in ['Name', 'Player', 'Position', 'Age']:
                player_map[name] = href
        
        return player_map
    
    async def get_player_data(self, player: dict, player_url: str = None) -> dict:
        """Get additional data for a player"""
        
        if not player_url:
            return player
        
        player_page = await self.browser.new_page()
        
        try:
            await player_page.goto(player_url, wait_until='networkidle', timeout=60000)
            await player_page.wait_for_timeout(3000)
            
            # Extract stats from player page
            html = await player_page.content()
            
            # Try to find total stats table
            stats = {
                'age': player.get('age', '-'),
                'apps': '-',
                'min': '-',
                'goal': '-',
                'assist': '-',
                'yellow_card': '-',
                'red_card': '-'
            }
            
            # Look for stats in HTML (simplified - adjust as needed)
            age_match = re.search(r'<h[12][^>]*>[^<]*\d{1,2}[^<]*</h[12]', html)
            if age_match:
                stats['age'] = re.search(r'\b(\d{1,2})\b', age_match.group(0)).group(1)
            
            # Extract from common patterns
            patterns = {
                'apps': r'Appearances?\s*(\d+)',
                'minutes': r'Minutes?\s*(\d+)',
                'goals': r'Goals?\s*(\d+)',
                'assists': r'Assists?\s*(\d+)',
                'yellow': r'Yellow\s+Cards?\s*(\d+)',
                'red': r'Red\s+Cards?\s*(\d+)'
            }
            
            for stat_name, pattern in patterns.items():
                match = re.search(pattern, html, re.IGNORECASE)
                if match and stat_name != 'age':
                    stats[stat_name] = match.group(1)
            
            return {**player, **stats}
            
        except Exception as e:
            print(f"⚠️ Error for {player['name']}: {e}")
            return player
        finally:
            await player_page.close()
    
    async def scrape_with_existing_data(self, team_id: str, team_name: str, country: str, league: str, existing_json_path: str = None) -> dict:
        """Scrape using existing data as base"""
        
        url = f"https://us.soccerway.com/team/{team_name.lower().replace(' ', '-')}/{team_id}/squad/"
        
        print(f"🎯 Scraping: {team_name}")
        
        # Load existing data
        if existing_json_path:
            with open(existing_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Handle both list and dict format
            players_data = data if isinstance(data, list) else data.get('players', data.get('teams', [{}])[0].get('players', []))
            print(f"✅ Loaded {len(players_data)} players from existing data")
        else:
            print("❌ No existing data")
            return None
        
        # Extract player links from squad page
        print("📋 Extracting player links from squad page...")
        player_links = await self.extract_player_links_from_squad(url)
        print(f"✅ Found {len(player_links)} player links")
        
        # For each player, try to get stats
        print("📊 Extracting stats...")
        
        final_players = []
        
        for player in players_data:
            name = player['name']
            player_url = player_links.get(name)
            
            if player_url:
                updated = await self.get_player_data(player, player_url)
                final_players.append(updated)
                print(f"  ✅ {name}: Age={updated.get('age', '-')}, Apps={updated.get('apps', '-')}")
            else:
                # No link found, use existing data
                final_players.append(player)
                print(f"  ⚠️ {name}: No link found")
            
            await asyncio.sleep(1)  # Rate limit
        
        # Format final output
        lineup_players = []
        for p in final_players:
            # Ensure position format
            pos = p.get('position', '-')
            if pos not in ['GK', 'DEF', 'MID', 'FWD']:
                if 'Goalkeeper' in pos:
                    pos = 'GK'
                elif 'Defender' in pos:
                    pos = 'DEF'
                elif 'Midfielder' in pos:
                    pos = 'MID'
                elif 'Forward' in pos:
                    pos = 'FWD'
            
            lineup_player = {
                "number": p.get('number', '-'),
                "name": p['name'],
                "national": p.get('national', '-'),
                "position": pos,
                "age": p.get('age', '-'),
                "apps": p.get('apps', '-'),
                "min": p.get('min', '-'),
                "goal": p.get('goal', '-'),
                "assist": p.get('assist', '-'),
                "yellow_card": p.get('yellow_card', '-'),
                "red_card": p.get('red_card', '-'),
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
        
        return {
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
    
    async def close(self):
        """Cleanup"""
        if self.base_page:
            await self.base_page.close()
        if self.browser:
            await self.browser.close()


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Soccerway Scraper')
    parser.add_argument('--id', '-i', required=True, help='Team ID')
    parser.add_argument('--name', '-n', required=True, help='Team name')
    parser.add_argument('--country', '-c', required=True, help='Country')
    parser.add_argument('--league', '-l', required=True, help='League')
    parser.add_argument('--existing', '-e', default='/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json', help='Path to existing player JSON')
    
    args = parser.parse_args()
    
    scraper = SmartScraper(concurrency=3)
    
    try:
        await scraper.initialize()
        
        result = await scraper.scrape_with_existing_data(
            team_id=args.id,
            team_name=args.name,
            country=args.country,
            league=args.league,
            existing_json_path=args.existing
        )
        
        if result:
            output_file = f"/home/openclaw/.openclaw/workspace/lineup_ai_{args.country.lower()}_{args.league.replace(' ', '-').lower()}_team_{args.name.lower()}_{args.id}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Summary
            with_stats = sum(1 for p in result['players'] if p['apps'] != '-')
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"{'='*60}")
            print(f"Team: {result['team']['name']}")
            print(f"Players: {len(result['players'])}")
            print(f"With stats: {with_stats}/{len(result['players'])}")
            print(f"Saved: {output_file}")
            
        else:
            print("❌ Failed")
            
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
