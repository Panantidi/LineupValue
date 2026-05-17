#!/usr/bin/env python3
"""
Full extraction with lazy loading + stealth
Solutions:
1. Scroll to trigger lazy loading
2. Add stealth to bypass fingerprint detection
3. Check for multiple tables
4. Wait for all rows to render
"""

import json
from playwright.sync_api import sync_playwright

def extract_all_players():
    """Extract ALL players using stealth + lazy loading"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        
        # Add stealth context
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768},
            locale='en-US',
            color_scheme='light'
        )
        
        # Add stealth script
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        page = context.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for initial render
        page.wait_for_timeout(5000)
        
        # Check for tables
        table_count = page.locator('table').count()
        row_count = page.locator('tr').count()
        print(f"Initial tables: {table_count}, rows: {row_count}")
        
        # Scroll to trigger lazy loading
        print("Scrolling to load all players...")
        page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight);
        """)
        
        # Wait for lazy content
        page.wait_for_timeout(5000)
        
        # Scroll multiple times to be sure
        for i in range(3):
            page.evaluate(f"""
                window.scrollTo(0, {i * 500 + 300});
            """)
            page.wait_for_timeout(1500)
        
        # Check again
        table_count = page.locator('table').count()
        row_count = page.locator('tr').count()
        print(f"After scroll - tables: {table_count}, rows: {row_count}")
        
        # Wait for lineup table specifically
        try:
            page.wait_for_selector('.lineupTable', timeout=10000)
            print("✅ Found lineupTable")
        except:
            print("⚠️ lineupTable not found, trying alternative")
        
        # Get all rows from lineup table
        lineup_table = page.query_selector("div.lineupTable")
        
        if lineup_table:
            rows = lineup_table.query_selector_all(".lineupTable__row")
            print(f"✅ Found {len(rows)} player rows in lineupTable")
            
            for i, row in enumerate(rows):
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 9:
                    continue
                
                try:
                    number = cells[0].text_content().strip() if cells[0] else ""
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
                    age = cells[2].text_content().strip() if len(cells) > 2 and cells[2] else ""
                    apps = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else ""
                    minutes = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else ""
                    goals = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else ""
                    assists = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else ""
                    yellow = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else ""
                    red = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else ""
                    
                    player = {
                        "number": number if number else "-",
                        "name": name,
                        "age": age if age else "-",
                        "apps": apps if apps else "-",
                        "min": minutes if minutes else "-",
                        "goal": goals if goals else "-",
                        "assist": assists if assists else "-",
                        "yellow_card": yellow if yellow else "-",
                        "red_card": red if red else "-"
                    }
                    
                    players.append(player)
                    
                    if i < 5:
                        print(f"  ✅ {number}. {name} | Age: {age} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error row {i}: {e}")
                    continue
        else:
            print("❌ No lineupTable found")
            
            # Try alternative tables
            all_tables = page.query_selector_all('table')
            print(f"Trying {len(all_tables)} alternative tables...")
            
            for table in all_tables[:5]:
                rows = table.query_selector_all("tr")
                if rows and len(rows) > 2:
                    print(f"  Found table with {len(rows)} rows")
                    # Could extract here...
        
        browser.close()
    
    return players


def main():
    print("=== Extracting ALL Strasbourg Players (with stealth + scroll) ===\n")
    
    players = extract_all_players()
    
    if players:
        print(f"\n✅ Extracted {len(players)} players")
        
        team_data = {
            "team": {
                "id": "nP6UzIU1",
                "name": "Strasbourg",
                "slug": "strasbourg",
                "league": "Ligue 1",
                "country": "France"
            },
            "matches": [],
            "players": players
        }
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        with_stats = sum(1 for p in players if p['min'] != "-")
        
        print(f"✅ Saved to: {output_file}")
        print(f"✅ Players with stats: {with_stats}/{len(players)}")
        
    else:
        print("❌ No players extracted")


if __name__ == "__main__":
    main()
