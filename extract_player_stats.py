#!/usr/bin/env python3
"""
Extract player stats from Soccerway for each player
Uses your working Playwright method
"""

import json
import re
from playwright.sync_api import sync_playwright
import time

def extract_player_stats(player_name, number, base_url):
    """Extract stats for a single player"""
    
    # Build player URL
    player_url = f"{base_url}/player/"
    
    # Find player link in the squad page
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Go to squad page
            page.goto("https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            
            # Find player link
            lineup_table = page.query_selector("div.lineupTable")
            if not lineup_table:
                browser.close()
                return None
            
            rows = lineup_table.query_selector_all(".lineupTable__row")
            
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                if len(cells) < 2:
                    continue
                
                # Get player name and number
                row_name = cells[1].text_content().strip()
                row_number = cells[0].text_content().strip()
                
                if row_name == player_name and (row_number == number or row_number == ""):
                    # Found player, get their page URL
                    name_link = row.query_selector(".lineupTable__cell--name a")
                    if not name_link:
                        continue
                    
                    player_url = name_link.get_attribute("href")
                    if not player_url:
                        continue
                    
                    # Navigate to player page
                    print(f"  Opening {player_url}")
                    page.goto(player_url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)
                    
                    # Extract stats from player page
                    html = page.content()
                    
                    # Look for stats table
                    stats = {
                        "apps": "-",
                        "min": "-",
                        "goal": "-",
                        "assist": "-",
                        "yellow_card": "-",
                        "red_card": "-"
                    }
                    
                    # Try to find total stats
                    total_pattern = r'<h3[^>]*>Total[^<]*</h3>.*?<table[^>]*>(.*?)</table>'
                    total_match = re.search(total_pattern, html, re.DOTALL)
                    
                    if total_match:
                        table_html = total_match.group(1)
                        
                        # Look for rows
                        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
                        
                        for row in rows:
                            if 'Apps' in row or 'Minutes' in row:
                                # Extract apps
                                apps_match = re.search(r'Apps?\s*(\d+)', row)
                                if apps_match:
                                    stats["apps"] = apps_match.group(1)
                                
                                # Extract minutes
                                min_match = re.search(r'Min(?:utes?)?\s*(\d+)', row)
                                if min_match:
                                    stats["min"] = min_match.group(1)
                                
                                # Extract goals
                                g_match = re.search(r'G\s*(\d+)', row)
                                if g_match:
                                    stats["goal"] = g_match.group(1)
                                
                                # Extract assists
                                a_match = re.search(r'A\s*(\d+)', row)
                                if a_match:
                                    stats["assist"] = a_match.group(1)
                                
                                # Extract yellow cards
                                yc_match = re.search(r'YC\s*(\d+)', row)
                                if yc_match:
                                    stats["yellow_card"] = yc_match.group(1)
                                
                                # Extract red cards
                                rc_match = re.search(r'RC\s*(\d+)', row)
                                if rc_match:
                                    stats["red_card"] = rc_match.group(1)
                    
                    browser.close()
                    return stats
            
            browser.close()
            return None
            
        except Exception as e:
            print(f"  Error: {e}")
            if 'browser' in locals():
                browser.close()
            return None


def main():
    print("=== Extracting Player Stats ===\n")
    
    # Load your Strasbourg JSON
    your_json_path = "/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json"
    
    with open(your_json_path, 'r', encoding='utf-8') as f:
        players_data = json.load(f)
    
    print(f"Found {len(players_data)} players")
    print("Extracting stats for each player...\n")
    
    stats_collection = []
    
    for i, player in enumerate(players_data):
        name = player['name']
        number = player['number']
        
        print(f"{i+1}. {name} ({number})...")
        
        stats = extract_player_stats(name, number, "https://us.soccerway.com")
        
        if stats:
            print(f"   ✅ Apps: {stats['apps']}, Min: {stats['min']}, G: {stats['goal']}, A: {stats['assist']}")
        else:
            print(f"   ⚠️ No stats found")
        
        stats_collection.append({
            "name": name,
            "number": number,
            "stats": stats
        })
        
        # Rate limiting - wait between requests
        time.sleep(2)
    
    # Combine with original data
    print("\n=== Combining data ===")
    
    combined = []
    for player in players_data:
        name = player['name']
        number = player['number']
        
        # Find stats
        player_stats = None
        for stat in stats_collection:
            if stat['name'] == name:
                player_stats = stat['stats']
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
        
        combined.append({
            "number": number,
            "name": name,
            "national": player.get('national', '-'),
            "position": pos_code,
            "age": "-",
            "apps": player_stats['apps'] if player_stats else "-",
            "min": player_stats['min'] if player_stats else "-",
            "goal": player_stats['goal'] if player_stats else "-",
            "assist": player_stats['assist'] if player_stats else "-",
            "yellow_card": player_stats['yellow_card'] if player_stats else "-",
            "red_card": player_stats['red_card'] if player_stats else "-",
            "last5": [],
            "_last5_details": [],
            "_last5_red_details": [],
            "_last5_yellow_details": [],
            "_last5_susp_details": [],
            "_last5_loan_details": [],
            "_last5_intl_details": [],
            "profile_path": "",
            "market_value": "-"
        })
    
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
    
    # Count players with stats
    with_stats = sum(1 for p in combined if p['apps'] != "-")
    
    print(f"\n✅ Saved {len(combined)} players to {output_file}")
    print(f"   Players with stats: {with_stats}/{len(combined)}")


if __name__ == "__main__":
    main()
