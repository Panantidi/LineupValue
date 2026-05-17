#!/usr/bin/env python3
"""
Extract Strasbourg squad using correct selectors
"""

from playwright.sync_api import sync_playwright
import json
import re

def extract_strasbourg():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = browser.new_page()
        
        print("Loading Strasbourg squad page...")
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)  # Wait for JS rendering
        
        # Find the squad table
        squad_table = page.query_selector("div.squad-table.profileTable")
        
        if not squad_table:
            print("No squad table found")
            browser.close()
            return None
        
        # Get all player rows from the table
        rows = squad_table.query_selector_all("tr")
        print(f"Found {len(rows)} rows in squad table")
        
        for row in rows:
            # Skip header rows
            if row.query_selector("th"):
                continue
            
            cells = row.query_selector_all("td")
            if len(cells) < 8:
                continue
            
            try:
                # Extract each cell
                jersey = cells[0].text_content().strip() if cells[0] else "-"
                
                # Player name is in second cell
                name_cell = cells[1]
                name_elem = name_cell.query_selector("a")
                name = name_elem.text_content().strip() if name_elem else name_cell.text_content().strip()
                
                nationality = cells[2].text_content().strip() if len(cells) > 2 and cells[2] else "-"
                position = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else "-"
                age = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else "-"
                apps = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else "-"
                minutes = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else "-"
                goals = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else "-"
                assists = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else "-"
                yellow = cells[9].text_content().strip() if len(cells) > 9 and cells[9] else "-"
                red = cells[10].text_content().strip() if len(cells) > 10 and cells[10] else "-"
                
                player = {
                    "number": jersey,
                    "name": name,
                    "national": nationality,
                    "position": position,
                    "age": age,
                    "apps": apps,
                    "min": minutes,
                    "goal": goals,
                    "assist": assists,
                    "yellow_card": yellow,
                    "red_card": red,
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
                print(f"  ✅ {jersey}. {name} - {position}, {age} apps: {apps}, g: {goals}")
                
            except Exception as e:
                print(f"  ⚠️ Error parsing row: {e}")
                continue
        
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
    print("=== Extracting Strasbourg Squad ===\n")
    
    players = extract_strasbourg()
    
    if players:
        team_data = create_json(players)
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Extracted {len(players)} players")
        print(f"✅ Saved to: {output_file}")
    else:
        print("❌ No data extracted")
