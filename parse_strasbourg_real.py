#!/usr/bin/env python3
"""
Parse Strasbourg squad from Soccerway using Playwright (Headless Chromium)
Extract: number, name, nationality, position, age, apps, minutes, goals, assists, yellow_cards, red_cards
"""

import json
import re
from playwright.sync_api import sync_playwright

def parse_strasbourg_squad():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    
    with sync_playwright() as p:
        # Launch Chromium headless with realistic settings
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"'
            ]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )
        
        page = context.new_page()
        
        try:
            print(f"Loading {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for JS to fully render
            print("Waiting for JS render...")
            page.wait_for_timeout(10000)
            
            # Check if we can find player data
            page_content = page.content()
            
            # Find all player links
            player_links = page.query_selector_all("a[href*='/player/']")
            print(f"Found {len(player_links)} player links in DOM")
            
            # Parse the HTML for player data
            # Look for table structure
            tables = page.query_selector_all("table")
            print(f"Found {len(tables)} tables")
            
            # Try to find squad stats table
            squad_table = page.query_selector("div.squad-table")
            if squad_table:
                print("Found squad table div")
                # Get all rows
                rows = squad_table.query_selector_all("tr")
                print(f"Found {len(rows)} rows in squad table")
                
                for row in rows:
                    # Skip header rows
                    if row.query_selector("th"):
                        continue
                    
                    cells = row.query_selector_all("td")
                    if len(cells) < 10:
                        continue
                    
                    try:
                        # Extract cell data
                        number = cells[0].text_content().strip() if cells[0] else "-"
                        
                        # Player name with link
                        name_cell = cells[1]
                        name_link = name_cell.query_selector("a")
                        name = name_link.text_content().strip() if name_link else name_cell.text_content().strip()
                        
                        # Nationality
                        nat_cell = cells[2] if len(cells) > 2 else None
                        nationality = nat_cell.text_content().strip() if nat_cell else "-"
                        
                        # Position
                        pos_cell = cells[3] if len(cells) > 3 else None
                        position = pos_cell.text_content().strip() if pos_cell else "-"
                        
                        # Age
                        age_cell = cells[4] if len(cells) > 4 else None
                        age = age_cell.text_content().strip() if age_cell else "-"
                        
                        # Apps
                        apps_cell = cells[5] if len(cells) > 5 else None
                        apps = apps_cell.text_content().strip() if apps_cell else "-"
                        
                        # Minutes
                        min_cell = cells[6] if len(cells) > 6 else None
                        minutes = min_cell.text_content().strip() if min_cell else "-"
                        
                        # Goals
                        goals_cell = cells[7] if len(cells) > 7 else None
                        goals = goals_cell.text_content().strip() if goals_cell else "-"
                        
                        # Assists
                        assists_cell = cells[8] if len(cells) > 8 else None
                        assists = assists_cell.text_content().strip() if assists_cell else "-"
                        
                        # Yellow cards
                        yc_cell = cells[9] if len(cells) > 9 else None
                        yellow_cards = yc_cell.text_content().strip() if yc_cell else "-"
                        
                        # Red cards
                        rc_cell = cells[10] if len(cells) > 10 else None
                        red_cards = rc_cell.text_content().strip() if rc_cell else "-"
                        
                        # Build player object
                        player = {
                            "number": number if number != "" else "-",
                            "name": name,
                            "national": nationality if nationality != "" else "-",
                            "position": position if position != "" else "-",
                            "age": age if age != "" else "-",
                            "apps": apps if apps != "" else "-",
                            "min": minutes if minutes != "" else "-",
                            "goal": goals if goals != "" else "-",
                            "assist": assists if assists != "" else "-",
                            "yellow_card": yellow_cards if yellow_cards != "" else "-",
                            "red_card": red_cards if red_cards != "" else "-",
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
                        print(f"  ✅ {number}. {name} | {nationality} | {position} | {age} | Apps: {apps} | Min: {minutes} | G: {goals} | A: {assists} | YC: {yellow_cards} | RC: {red_cards}")
                        
                    except Exception as e:
                        print(f"  ⚠️ Error parsing row: {e}")
                        continue
            else:
                print("❌ No squad table found")
                print("Available selectors:")
                # Debug: print all divs
                divs = page.query_selector_all("div")
                print(f"Found {len(divs)} divs")
            
            browser.close()
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            if 'browser' in locals():
                browser.close()
    
    return players


def create_json(players):
    return {
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


if __name__ == "__main__":
    print("=== Parsing Strasbourg from Soccerway (Real Data) ===\n")
    
    players = parse_strasbourg_squad()
    
    if players:
        team_data = create_json(players)
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Extracted {len(players)} players from Soccerway")
        print(f"✅ Saved to: {output_file}")
    else:
        print("❌ No data extracted from Soccerway")
