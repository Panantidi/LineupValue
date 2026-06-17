import asyncio
import json
import re
from playwright.async_api import async_playwright

async def fetch_japan_j1():
    url = 'https://www.soccerway.com/japan/j1-league/standings/6msfOkrp/standings/overall/'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Set timeout and wait for network
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Get page content
            html = await page.content()
            
            # Find team links in the rendered page
            teams = []
            
            # Look for table rows with team data
            rows = await page.query_selector_all('table tr')
            print(f'Found {len(rows)} table rows')
            
            for row in rows:
                # Find team link
                link = await row.query_selector('a[href*="/teams/"]')
                if link:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if href and text:
                        # Extract team ID from URL
                        match = re.search(r'/teams/[^/]+/([A-Za-z0-9]+)/?$', href)
                        if match:
                            team_id = match.group(1)
                            # Extract slug
                            slug_match = re.search(r'/teams/([^/]+)/([A-Za-z0-9]+)', href)
                            slug = slug_match.group(1) if slug_match else team_id
                            teams.append({
                                'id': team_id,
                                'name': text.strip(),
                                'slug': slug
                            })
                            print(f'Found: {text.strip()} ({team_id})')
            
            if not teams:
                # Try alternative: find all team links
                links = await page.query_selector_all('a[href*="/teams/"]')
                seen = set()
                for link in links:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if href and text:
                        match = re.search(r'/teams/[^/]+/([A-Za-z0-9]+)', href)
                        if match:
                            team_id = match.group(1)
                            if team_id not in seen:
                                seen.add(team_id)
                                slug_match = re.search(r'/teams/([^/]+)/([A-Za-z0-9]+)', href)
                                slug = slug_match.group(1) if slug_match else team_id
                                teams.append({
                                    'id': team_id,
                                    'name': text.strip(),
                                    'slug': slug
                                })
                                print(f'Found: {text.strip()} ({team_id})')
            
            print(f'\nTotal teams: {len(teams)}')
            return teams
            
        finally:
            await browser.close()

if __name__ == '__main__':
    teams = asyncio.run(fetch_japan_j1())
    
    if teams:
        # Load existing leagues_data.json
        try:
            with open('/home/openclaw/FormAlert/leagues_data.json', 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        
        # Add Japan J1 League
        if 'Japan' not in data:
            data['Japan'] = {}
        
        data['Japan']['J1 League'] = teams
        
        # Save
        with open('/home/openclaw/FormAlert/leagues_data.json', 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f'\nSaved {len(teams)} teams to leagues_data.json')