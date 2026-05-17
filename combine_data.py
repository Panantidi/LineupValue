#!/usr/bin/env python3
"""
Combine Strasbourg data from your JSON + Soccerway stats
"""

import json
import re
from playwright.sync_api import sync_playwright

def get_soccerway_stats(team_id):
    """Get stats from Soccerway squad page"""
    
    url = f"https://us.soccerway.com/team/strasbourg/{team_id}/squad/"
    
    stats = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)
            
            lineup_table = page.query_selector("div.lineupTable")
            if not lineup_table:
                browser.close()
                return stats
            
            rows = lineup_table.query_selector_all(".lineupTable__row")
            
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                if len(cells) < 9:
                    continue
                
                # Extract data
                number = cells[0].text_content().strip()
                name = cells[1].text_content().strip()
                age = cells[2].text_content().strip()
                apps = cells[3].text_content().strip()
                minutes = cells[4].text_content().strip()
                goals = cells[5].text_content().strip()
                assists = cells[6].text_content().strip()
                yellow = cells[7].text_content().strip()
                red = cells[8].text_content().strip()
                
                stats[number] = {
                    "number": number,
                    "name": name,
                    "age": age,
                    "apps": apps,
                    "min": minutes,
                    "goal": goals,
                    "assist": assists,
                    "yellow_card": yellow,
                    "red_card": red
                }
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
    
    return stats


def main():
    # Load your Strasbourg JSON
    your_json_path = "/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json"
    
    print("Loading your Strasbourg data...")
    with open(your_json_path, 'r', encoding='utf-8') as f:
        your_data = json.load(f)
    
    print(f"Found {len(your_data)} players")
    
    # Get Soccerway stats
    print("\nFetching stats from Soccerway...")
    soccerway_stats = get_soccerway_stats("nP6UzIU1")
    print(f"Found {len(soccerway_stats)} players with stats")
    
    # Combine
    print("\nCombining data...")
    combined = []
    
    for player in your_data:
        number = player['number']
        name = player['name']
        
        # Find matching player in Soccerway stats
        sw_stat = None
        for sw_player in soccerway_stats.values():
            if sw_player['name'] == name:
                sw_stat = sw_stat
                break
        
        # Map position
        if 'Goalkeeper' in player['position']:
            pos_code = 'GK'
        elif 'Defender' in player['position']:
            pos_code = 'DEF'
        elif 'Midfielder' in player['position']:
            pos_code = 'MID'
        else:
            pos_code = 'FWD'
        
        # Use stats from Soccerway if available, otherwise use your data
        if sw_stat:
            player_data = {
                "number": sw_stat['number'],
                "name": sw_stat['name'],
                "national": player['national'] if 'national' in player else '-',
                "position": pos_code,
                "age": sw_stat['age'],
                "apps": sw_stat['apps'],
                "min": sw_stat['min'],
                "goal": sw_stat['goal'],
                "assist": sw_stat['assist'],
                "yellow_card": sw_stat['yellow_card'],
                "red_card": sw_stat['red_card'],
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
        else:
            player_data = {
                "number": number,
                "name": name,
                "national": player['national'] if 'national' in player else '-',
                "position": pos_code,
                "age": player.get('age', '-'),
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
        
        combined.append(player_data)
    
    # Save
    team_data = {
        "team": {
            "id": "nP6UzIU1",
            "name": "Strasbourg",
            "slug": "strasbourg",
            "league": "Ligue 1",
            "country": "France"
        },
        "matches": [],
        "players": combined
    }
    
    output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved {len(combined)} players to {output_file}")
    
    # Show summary
    with_stats = sum(1 for p in combined if p['apps'] != "-")
    print(f"Players with stats: {with_stats}/{len(combined)}")


if __name__ == "__main__":
    main()
