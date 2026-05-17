#!/usr/bin/env python3
"""
Parse team squads from Soccerway using Playwright/Chromium
Saves data to JSON files in workspace
"""

import json
import os
import glob
from playwright.sync_api import sync_playwright

DATA_DIR = "/home/openclaw/.openclaw/workspace"

def get_team_data(team_id: str, team_name: str, league: str, country: str) -> dict:
    """Fetch squad data from Soccerway for a specific team"""
    
    # Soccerway URL for team squad
    url = f"https://us.soccerway.com/team/{team_name.replace(' ', '-')}/{team_id}/squad/"
    
    players = []
    
    with sync_playwright() as p:
        # Launch Chromium
        browser = p.chromium.launch(headless=True, args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage'
        ])
        page = browser.new_page()
        
        try:
            # Navigate to squad page
            print(f"Fetching {team_name}...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for squad table
            try:
                page.wait_for_selector("table.table-squad", timeout=10000)
            except:
                # Try alternative selector
                page.wait_for_selector("table.squad-stats", timeout=5000)
            
            # Extract team info
            team_data = {
                "team": {
                    "id": team_id,
                    "name": team_name,
                    "slug": team_name.lower().replace(" ", "-").replace("'", ""),
                    "league": league,
                    "country": country
                },
                "matches": [],  # Will populate from fixtures
                "players": []
            }
            
            # Extract players from table
            rows = page.query_selector_all("table.table-squad tbody tr, table.squad-stats tbody tr")
            
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 10:
                    continue
                
                # Extract player data (adjust selectors based on actual Soccerway structure)
                player = {
                    "number": cells[0].text_content().strip() if cells[0] else "-",
                    "name": cells[1].text_content().strip() if len(cells) > 1 and cells[1] else "-",
                    "national": cells[2].text_content().strip() if len(cells) > 2 and cells[2] else "-",
                    "position": cells[3].text_content().strip() if len(cells) > 3 and cells[3] else "-",
                    "age": cells[4].text_content().strip() if len(cells) > 4 and cells[4] else "-",
                    "apps": cells[5].text_content().strip() if len(cells) > 5 and cells[5] else "-",
                    "min": cells[6].text_content().strip() if len(cells) > 6 and cells[6] else "-",
                    "goal": cells[7].text_content().strip() if len(cells) > 7 and cells[7] else "-",
                    "assist": cells[8].text_content().strip() if len(cells) > 8 and cells[8] else "-",
                    "market_value": cells[9].text_content().strip() if len(cells) > 9 and cells[9] else "-",
                    "yellow_card": cells[10].text_content().strip() if len(cells) > 10 and cells[10] else "-",
                    "red_card": cells[11].text_content().strip() if len(cells) > 11 and cells[11] else "-",
                    "last5": ["SUB", "SUB", "SUB", "SUB", "SUB"],  # Default - would parse from match history
                    "profile_path": "",  # Would extract from profile link
                    "market_value": "",
                    "last5": [],  # Empty - need to parse from match history page
                    "_last5_details": [],
                    "_last5_red_details": [],
                    "_last5_yellow_details": [],
                    "_last5_susp_details": [],
                    "_last5_loan_details": [],
                    "_last5_intl_details": []
                }
                
                # Extract nationality flag URL if available
                flag_img = cells[2].query_selector("img") if len(cells) > 2 and cells[2] else None
                if flag_img:
                    player["national"] = {
                        "name": cells[2].text_content().strip(),
                        "code": cells[2].text_content().strip(),
                        "flag": flag_img.get_attribute("src") or ""
                    }
                
                players.append(player)
            
            print(f"  Found {len(players)} players")
            team_data["players"] = players
            
            # Try to get recent matches
            try:
                fixtures_link = page.query_selector("a[href*='/fixtures']")
                if fixtures_link:
                    fixtures_url = "https://us.soccerway.com" + fixtures_link.get_attribute("href")
                    page.goto(fixtures_url, wait_until="networkidle", timeout=30000)
                    matches = []
                    match_rows = page.query_selector_all("table.table-fixtures tbody tr")
                    for match_row in match_rows[:5]:  # Last 5 matches
                        cells = match_row.query_selector_all("td")
                        if len(cells) >= 3:
                            match = {
                                "date": cells[0].text_content().strip() if cells[0] else "",
                                "comp": cells[1].text_content().strip() if len(cells) > 1 and cells[1] else "",
                                "comp_full": "",
                                "url": "https://us.soccerway.com" + (match_row.query_selector("a") or {}).get_attribute("href") or ""
                            }
                            matches.append(match)
                    team_data["matches"] = matches
            except:
                pass
            
            browser.close()
            return team_data
            
        except Exception as e:
            print(f"  Error: {e}")
            browser.close()
            return None


def main():
    """Parse squads for all teams in the hierarchy"""
    
    # Load team hierarchy
    import sys
    sys.path.insert(0, '/home/openclaw/FormAlert')
    from lineup_data_complete import load_complete_hierarchy
    
    hierarchy = load_complete_hierarchy()
    
    parsed_count = 0
    error_count = 0
    
    for country, leagues in hierarchy.items():
        for league_name, teams in leagues.items():
            print(f"\n{country} - {league_name}")
            
            for team in teams:
                team_id = team["id"]
                team_name = team["name"]
                
                # Check if file already exists
                existing_file = None
                for f in glob.glob(f"{DATA_DIR}/lineup_ai_*.json"):
                    if team_id in f:
                        existing_file = f
                        break
                
                if existing_file:
                    print(f"  Skipping {team_name} (already exists)")
                    continue
                
                # Parse team data
                data = get_team_data(team_id, team_name, league_name, country)
                
                if data:
                    # Save to JSON file
                    league_slug = league_name.lower().replace(" ", "-").replace("/", "-")
                    team_slug = team_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
                    filename = f"lineup_ai_{league_slug}_team_{team_slug}_{team_id}.json"
                    filepath = os.path.join(DATA_DIR, filename)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    print(f"  ✅ Saved {filepath}")
                    parsed_count += 1
                else:
                    print(f"  ❌ Failed to parse {team_name}")
                    error_count += 1
    
    print(f"\n=== Summary ===")
    print(f"✅ Parsed: {parsed_count} teams")
    print(f"❌ Errors: {error_count} teams")


if __name__ == "__main__":
    main()
