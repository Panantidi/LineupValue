#!/usr/bin/env python3
"""
Parse Soccerway squad using advanced Playwright techniques
Multiple strategies to bypass anti-bot
"""

import json
import time
from playwright.sync_api import sync_playwright

def parse_with_strategy(team_id, team_name, country, league, url):
    """Try multiple strategies to get squad data"""
    
    strategies = [
        # Strategy 1: Standard Playwright
        {
            "name": "Standard",
            "headless": True,
            "args": ['--no-sandbox', '--disable-setuid-sandbox'],
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        # Strategy 2: Mobile user agent
        {
            "name": "Mobile",
            "headless": True,
            "args": ['--no-sandbox', '--disable-setuid-sandbox'],
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        },
        # Strategy 3: Longer wait times
        {
            "name": "LongWait",
            "headless": True,
            "args": ['--no-sandbox', '--disable-setuid-sandbox'],
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    ]
    
    for strategy in strategies:
        print(f"\n=== Trying {strategy['name']} strategy ===")
        
        players = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=strategy['headless'],
                args=strategy['args']
            )
            
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent=strategy['user_agent']
            )
            
            page = context.new_page()
            
            try:
                print(f"Loading {url}...")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for content
                if strategy['name'] == 'LongWait':
                    page.wait_for_timeout(15000)
                else:
                    page.wait_for_timeout(8000)
                
                # Get page content
                html = page.content()
                
                # Check if we have player data
                if 'player' in html.lower() or '/player/' in html:
                    print("✅ Found player data in DOM")
                    
                    # Parse HTML
                    import re
                    
                    # Find all player names
                    name_pattern = r'<a[^>]+href="[^"]*/player/[^"]*"[^>]*>([^<]+)</a>'
                    names = re.findall(name_pattern, html)
                    print(f"Found {len(names)} player names")
                    
                    # Find jersey numbers
                    number_pattern = r'<td[^>]*>(\d{1,3})\s*</td>'
                    numbers = re.findall(number_pattern, html)
                    print(f"Found {len(numbers)} jersey numbers")
                    
                    # Find nationality (usually in img alt or span)
                    nat_pattern = r'alt="([^"]+)"[^>]*class="flag"'
                    nationalities = re.findall(nat_pattern, html)
                    print(f"Found {len(nationalities)} nationalities")
                    
                    # Extract stats - look for table structure
                    # This is tricky - need to find the right table
                    table_patterns = [
                        r'<table[^>]*class="[^"]*table[^"]*"[^>]*>(.*?)</table>',
                        r'<div[^>]*class="[^"]*squad[^"]*"[^>]*>(.*?)</div>',
                    ]
                    
                    for table_pattern in table_patterns:
                        tables = re.findall(table_pattern, html, re.DOTALL)
                        if tables:
                            print(f"Found {len(tables)} tables")
                            
                            # Try to parse first table
                            for i, table in enumerate(tables[:3]):
                                # Find rows
                                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
                                print(f"  Table {i}: {len(rows)} rows")
                                
                                # Parse rows
                                for row in rows:
                                    # Check if it has player data
                                    if '<td' not in row:
                                        continue
                                    
                                    # Extract cells
                                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                                    if len(cells) < 8:
                                        continue
                                    
                                    # Skip header rows
                                    if any('Name' in c or 'Number' in c or 'Age' in c for c in cells):
                                        continue
                                    
                                    # Try to extract player data
                                    try:
                                        # Number should be first
                                        number = cells[0].strip() if cells[0].strip() and cells[0].strip().isdigit() else "-"
                                        
                                        # Name is in link
                                        name_match = re.search(r'<a[^>]*>([^<]+)</a>', cells[1])
                                        name = name_match.group(1).strip() if name_match else cells[1].strip()
                                        
                                        if name and name not in ['Name', 'Position', 'Age']:
                                            player = {
                                                "number": number if number != "" else "-",
                                                "name": name,
                                                "national": "-",  # Will fill later
                                                "position": "-",
                                                "age": "-",
                                                "apps": "-",
                                                "min": "-",
                                                "goal": "-",
                                                "assist": "-",
                                                "yellow_card": "-",
                                                "red_card": "-",
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
                                            
                                            players.append(player)
                                            print(f"    ✅ {number}. {name}")
                                            
                                            if len(players) >= 10:
                                                break
                                    except Exception as e:
                                        continue
                                
                                if len(players) >= 10:
                                    break
                    
                    if players:
                        print(f"\n✅ Successfully extracted {len(players)} players")
                        return players
                
                else:
                    print("❌ No player data found in DOM")
                    # Save HTML for debugging
                    with open(f'/tmp/{team_name}_strat_{strategy["name"]}.html', 'w') as f:
                        f.write(html)
                    print(f"Saved HTML to /tmp/{team_name}_strat_{strategy['name']}.html")
            
            except Exception as e:
                print(f"❌ Error: {e}")
            finally:
                browser.close()
        
        # Wait before next strategy
        time.sleep(2)
    
    return []


def main():
    """Parse multiple teams"""
    
    teams = [
        {
            "id": "nP6UzIU1",
            "name": "Strasbourg",
            "country": "France",
            "league": "Ligue 1",
            "url": "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
        },
        {
            "id": "nQ7VwKx2",
            "name": "Monaco",
            "country": "France", 
            "league": "Ligue 1",
            "url": "https://us.soccerway.com/team/monaco/nQ7VwKx2/squad/"
        },
        {
            "id": "nR8XyLz3",
            "name": "Lens",
            "country": "France",
            "league": "Ligue 1", 
            "url": "https://us.soccerway.com/team/lens/nR8XyLz3/squad/"
        }
    ]
    
    all_data = []
    
    for team in teams:
        print(f"\n{'='*60}")
        print(f"PARSING: {team['name']}")
        print(f"{'='*60}")
        
        players = parse_with_strategy(
            team['id'],
            team['name'],
            team['country'],
            team['league'],
            team['url']
        )
        
        if players:
            team_data = {
                "team": {
                    "id": team['id'],
                    "name": team['name'],
                    "slug": team['name'].lower().replace(' ', '-'),
                    "league": team['league'],
                    "country": team['country']
                },
                "matches": [],
                "players": players
            }
            
            output_file = f"/home/openclaw/.openclaw/workspace/lineup_ai_{team['country'].lower()}_{team['league'].replace(' ', '-').lower()}_team_{team['name'].lower()}_{team['id']}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(team_data, f, indent=2, ensure_ascii=False)
            
            all_data.append({
                "team": team['name'],
                "players": len(players),
                "file": output_file
            })
            
            print(f"✅ Saved {len(players)} players to {output_file}")
        else:
            print(f"❌ No data extracted for {team['name']}")
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for data in all_data:
        print(f"{data['team']}: {data['players']} players")


if __name__ == "__main__":
    main()
