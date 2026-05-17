#!/usr/bin/env python3
"""
Smart Enrichment Pipeline using XHR/Fetch interception
Strategy:
1. Load roster JSON (source of truth)
2. Open squad page and intercept all network requests
3. Capture API endpoints with stats data
4. Extract JSON directly (no DOM parsing)
5. Enrich roster with stats
"""

import json
import re
import asyncio
from playwright.async_api import async_playwright
from typing import Dict, List, Any
from datetime import datetime


class SoccerwayEnricher:
    """Enrich roster using intercepted API responses"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.page = None
        self.intercepted_data = {}
        self.requests = []
        
    async def initialize(self):
        """Initialize browser with request interception"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        self.page = await context.new_page()
        
        # Set up request interception
        await self.page.route("**/*", self._handle_request)
        
    async def _handle_request(self, route):
        """Intercept all requests and log them"""
        url = route.request.url
        
        # Log interesting requests
        if any(keyword in url.lower() for keyword in ['player', 'stats', 'performance', 'match', 'team']):
            self.requests.append({
                'url': url,
                'method': route.request.method,
                'timestamp': datetime.now().isoformat()
            })
        
        # Continue request
        await route.continue_()
    
    async def intercept_responses(self, squad_url: str, player_names: List[str]):
        """Navigate to squad page and capture API responses"""
        
        await self.page.goto(squad_url, wait_until='networkidle', timeout=60000)
        await self.page.wait_for_timeout(10000)
        
        # Wait for more requests
        await self.page.wait_for_timeout(15000)
        
        # Capture all console logs and network data
        print(f"Intercepted {len(self.requests)} requests")
        
        # Print interesting URLs
        print("\n📡 Intercepted API endpoints:")
        for req in self.requests:
            if any(kw in req['url'].lower() for kw in ['api', 'player', 'stats', 'performance', 'data']):
                print(f"  📄 {req['url']}")
        
        # Try to get page state
        try:
            page_state = await self.page.evaluate("""() => {
                return {
                    initialState: window.__INITIAL_STATE__ ? 'FOUND' : 'NOT_FOUND',
                    nextData: window.__NEXT_DATA__ ? 'FOUND' : 'NOT_FOUND',
                    appData: document.querySelector('script[type="application/ld+json"]') ? 'FOUND' : 'NOT_FOUND'
                };
            }""")
            print(f"\n🔍 Page state: {page_state}")
        except Exception as e:
            print(f"\n⚠️ Could not check page state: {e}")
    
    def get_api_stats(self, player_name: str, player_number: str = None):
        """
        Try to find stats from intercepted requests
        This is a placeholder - you'll need to analyze the actual URLs
        """
        # Look for player-specific stats
        for req in self.requests:
            if player_name.lower() in req['url'].lower() or (player_number and player_number in req['url']):
                # Extract player ID from URL
                match = re.search(r'/player/([^/]+)/', req['url'])
                if match:
                    player_id = match.group(1)
                    return {
                        'player_id': player_id,
                        'stats_url': req['url']
                    }
        return None


async def main():
    """Main enrichment pipeline"""
    
    print("=== Soccerway Enrichment Pipeline ===\n")
    
    # Load Strasbourg roster (your source of truth)
    roster_path = '/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json'
    
    print(f"Loading roster from: {roster_path}")
    with open(roster_path, 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    print(f"✅ Loaded {len(roster)} players\n")
    
    # Extract player names
    player_names = [p['name'] for p in roster]
    player_numbers = {p['name']: p['number'] for p in roster}
    
    # Initialize enricher
    enricher = SoccerwayEnricher(headless=True)
    
    try:
        await enricher.initialize()
        
        # Navigate to squad page
        squad_url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
        print(f"\nNavigating to: {squad_url}")
        
        await enricher.intercept_responses(squad_url, player_names)
        
        # Analyze intercepted requests
        print(f"\n📊 Analysis:")
        print(f"  Total requests: {len(enricher.requests)}")
        
        # Look for player stats endpoints
        player_endpoints = []
        for req in enricher.requests:
            url = req['url']
            if '/player/' in url and ('stats' in url or 'performance' in url or 'matches' in url):
                player_endpoints.append(req)
        
        print(f"  Player endpoints found: {len(player_endpoints)}")
        
        for ep in player_endpoints[:5]:
            print(f"    - {ep['url']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if enricher.page:
            await enricher.page.close()
        if enricher.browser:
            await enricher.browser.close()
    
    print(f"\n💡 Next steps:")
    print(f"1. Analyze intercepted URLs")
    print(f"2. Create specific endpoints parser")
    print(f"3. Fetch stats from each endpoint")
    print(f"4. Enrich roster JSON")


if __name__ == "__main__":
    asyncio.run(main())
