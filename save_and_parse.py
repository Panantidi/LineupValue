#!/usr/bin/env python3
"""
Save Strasbourg squad page HTML and parse it
Uses YOUR working method from earlier
"""

from playwright.sync_api import sync_playwright
import json
import re

def save_squad_page():
    """Save Strasbourg squad page using your selectors"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        page = browser.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for JS to render
        print("Waiting for squad to render...")
        page.wait_for_timeout(12000)  # Extended wait
        
        # Check if lineup table exists
        lineup_table = page.query_selector("div.lineupTable")
        if not lineup_table:
            print("❌ No lineup table found")
            browser.close()
            return None
        
        # Get full HTML
        html = page.content()
        print(f"✅ HTML saved: {len(html)} chars")
        
        # Save to file
        output_file = "/tmp/strasbourg_squad_full.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"✅ Saved to: {output_file}")
        
        # Now parse the HTML
        print("\n=== Parsing HTML ===\n")
        
        # Find ALL players in the HTML
        players = []
        
        # Pattern 1: Players in lineup table
        print("Looking for players in lineup table...")
        
        # Find all rows
        rows = re.findall(r'<tr[^>]*class="[^"]*lineupTable__row[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        
        print(f"Found {len(rows)} rows in lineup table")
        
        for row in rows:
            # Skip header rows
            if '<th' in row:
                continue
            
            # Extract cells
            cells = re.findall(r'<td[^>]*class="[^"]*lineupTable__cell[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL)
            
            if len(cells) < 9:
                continue
            
            try:
                # Number
                number = re.sub(r'<[^>]+>', '', cells[0]).strip()
                
                # Name (from link)
                name_match = re.search(r'<a[^>]+href="[^"]*player[^"]*"[^>]*>([^<]+)</a>', cells[1])
                name = name_match.group(1).strip() if name_match else re.sub(r'<[^>]+>', '', cells[1]).strip()
                
                # Age
                age = re.sub(r'<[^>]+>', '', cells[2]).strip()
                
                # Apps
                apps = re.sub(r'<[^>]+>', '', cells[3]).strip()
                
                # Minutes
                minutes = re.sub(r'<[^>]+>', '', cells[4]).strip()
                
                # Goals
                goals = re.sub(r'<[^>]+>', '', cells[5]).strip()
                
                # Assists
                assists = re.sub(r'<[^>]+>', '', cells[6]).strip()
                
                # Yellow cards
                yellow = re.sub(r'<[^>]+>', '', cells[7]).strip()
                
                # Red cards
                red = re.sub(r'<[^>]+>', '', cells[8]).strip()
                
                # Get nationality from flag image
                national = "-"
                nat_match = re.search(r'alt="([^"]+)"', cells[1])
                if nat_match:
                    national = nat_match.group(1)
                else:
                    # Try other cells
                    for cell in cells[2:5]:
                        nat_match = re.search(r'alt="([^"]+)"', cell)
                        if nat_match:
                            national = nat_match.group(1)
                            break
                
                player = {
                    "number": number,
                    "name": name,
                    "national": national,
                    "position": "-",
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
                print(f"  ✅ {number}. {name} | {national} | Age: {age} | Apps: {apps} | Min: {minutes} | G: {goals} | A: {assists}")
                
            except Exception as e:
                print(f"  ⚠️ Error parsing row: {e}")
                continue
        
        browser.close()
        
        return players, html


def merge_with_your_data(players_with_stats, your_json_path):
    """Merge stats with your data (which has positions)"""
    
    # Load your JSON
    with open(your_json_path, 'r', encoding='utf-8') as f:
        your_data = json.load(f)
    
    print(f"\n=== Merging data ===")
    print(f"Your data: {len(your_data)} players")
    print(f"Stats data: {len(players_with_stats)} players")
    
    combined = []
    
    for player in your_data:
        name = player['name']
        number = player['number']
        
        # Find matching player with stats
        stats_player = None
        for sp in players_with_stats:
            if sp['name'] == name:
                stats_player = sp
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
        
        if stats_player:
            combined.append({
                "number": stats_player['number'],
                "name": stats_player['name'],
                "national": stats_player['national'],
                "position": pos_code,
                "age": stats_player['age'],
                "apps": stats_player['apps'],
                "min": stats_player['min'],
                "goal": stats_player['goal'],
                "assist": stats_player['assist'],
                "yellow_card": stats_player['yellow_card'],
                "red_card": stats_player['red_card'],
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
        else:
            # No stats, use your data with dashes
            combined.append({
                "number": number,
                "name": name,
                "national": player.get('national', '-'),
                "position": pos_code,
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
            })
    
    return combined


def main():
    your_json_path = "/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json"
    
    result = save_squad_page()
    
    if not result:
        print("❌ Failed to save squad page")
        return
    
    players_with_stats, html = result
    
    print(f"\n✅ Extracted {len(players_with_stats)} players with stats")
    
    # Merge with your data
    combined = merge_with_your_data(players_with_stats, your_json_path)
    
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
    
    # Count
    with_stats = sum(1 for p in combined if p['apps'] != "-")
    
    print(f"\n✅ Final: {len(combined)} players")
    print(f"   With stats: {with_stats}")
    print(f"   Saved to: {output_file}")
    
    # Show first few
    print(f"\n=== Sample players ===")
    for p in combined[:3]:
        print(f"  {p['number']}. {p['name']} | {p['national']} | {p['position']} | Apps: {p['apps']}, G: {p['goal']}, A: {p['assist']}")


if __name__ == "__main__":
    main()
