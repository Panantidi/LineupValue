#!/usr/bin/env python3
"""
Extract Strasbourg squad data from Soccerway
"""

import json
import os
from playwright.sync_api import sync_playwright

def extract_strasbourg_squad():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        page = browser.new_page()
        
        try:
            print(f"Loading {url}...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait for squad table to load
            page.wait_for_selector("table.table-squad", timeout=15000)
            
            print("Extracting player data...")
            
            # Get all player rows
            rows = page.query_selector_all("table.table-squad tbody tr")
            
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 10:
                    continue
                
                try:
                    # Extract data based on Soccerway structure
                    # Columns typically: #, Name, Nat, Pos, Age, Apps, Min, G, A, YC, RC
                    number = cells[0].text_content().strip() if cells[0] else "-"
                    name = cells[1].text_content().strip() if len(cells) > 1 and cells[1] else "-"
                    
                    # Nationality
                    if len(cells) > 2 and cells[2]:
                        nat_text = cells[2].text_content().strip()
                        # Check if there's a flag image
                        flag_img = cells[2].query_selector("img")
                        if flag_img:
                            flag_url = flag_img.get_attribute("src") or ""
                            national = {
                                "name": nat_text,
                                "code": nat_text,  # Simplified - would need parsing
                                "flag": flag_url
                            }
                        else:
                            national = nat_text
                    else:
                        national = "-"
                    
                    position = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else "-"
                    age = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else "-"
                    apps = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else "-"
                    minutes = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else "-"
                    goals = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else "-"
                    assists = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else "-"
                    yellow_cards = cells[9].text_content().strip() if len(cells) > 9 and cells[9] else "-"
                    red_cards = cells[10].text_content().strip() if len(cells) > 10 and cells[10] else "-"
                    
                    # Build player object
                    player = {
                        "number": number,
                        "name": name,
                        "national": national,
                        "position": position,
                        "age": age,
                        "apps": apps,
                        "min": minutes,
                        "goal": goals,
                        "assist": assists,
                        "yellow_card": yellow_cards,
                        "red_card": red_cards,
                        # Add default empty arrays for last5
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
                    print(f"  ✅ {number}. {name} ({position}, {age})")
                    
                except Exception as e:
                    print(f"  ⚠️ Error parsing row: {e}")
                    continue
            
            print(f"\n✅ Extracted {len(players)} players")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()
    
    return players


def create_json(players):
    """Create full JSON structure"""
    return {
        "team": {
            "id": "nP6UzIU1",
            "name": "Strasbourg",
            "slug": "strasbourg",
            "league": "Ligue 1",
            "country": "France"
        },
        "matches": [],  # Would fetch from fixtures page
        "players": players
    }


if __name__ == "__main__":
    print("=== Extracting Strasbourg Squad ===\n")
    
    players = extract_strasbourg_squad()
    
    if players:
        team_data = create_json(players)
        
        # Save to file
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved to: {output_file}")
        print(f"   Total players: {len(players)}")
    else:
        print("❌ No data extracted")
