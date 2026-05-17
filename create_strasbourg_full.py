#!/usr/bin/env python3
"""
Create full Strasbourg squad JSON using your working Chromium method
Extracts: Number, Name, Age, Min, Goal, Assist, Yellow, Red
"""

import json
from playwright.sync_api import sync_playwright

def extract_strasbourg_stats():
    """Extract Strasbourg stats using your working method"""
    
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
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for squad table to render
        print("Waiting for squad to render...")
        page.wait_for_timeout(10000)
        
        # Get the lineup table
        lineup_table = page.query_selector("div.lineupTable")
        
        if not lineup_table:
            print("❌ No lineup table found")
            browser.close()
            return None
        
        # Get all player rows
        rows = lineup_table.query_selector_all(".lineupTable__row")
        print(f"Found {len(rows)} player rows")
        
        for row in rows:
            cells = row.query_selector_all(".lineupTable__cell")
            
            if len(cells) < 9:
                continue
            
            try:
                # Extract data based on your successful extraction
                number = cells[0].text_content().strip() if cells[0] else ""
                name = cells[1].text_content().strip() if cells[1] else ""
                
                # Skip if no name
                if not name or name in ['Name', 'Number', 'Position', 'Age']:
                    continue
                
                # Extract stats from cells
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
                print(f"  ✅ {number}. {name} | Age: {age} | Apps: {apps} | Min: {minutes} | G: {goals} | A: {assists} | YC: {yellow} | RC: {red}")
                
            except Exception as e:
                print(f"  ⚠️ Error parsing row: {e}")
                continue
        
        browser.close()
    
    return players


def create_full_json(stats_data):
    """Merge with your existing roster data (names, positions)"""
    
    # Load your existing roster
    roster_path = '/home/openclaw/.openclaw/media/inbound/strasbourg_squad---b11c9f6f-4aff-4a9b-8307-586a8f07643d.json'
    
    with open(roster_path, 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    print(f"\n✅ Loaded {len(roster)} players from roster")
    print(f"✅ Loaded {len(stats_data)} players from stats\n")
    
    # Create mapping from stats
    stats_map = {}
    for s in stats_data:
        name = s['name']
        number = s['number']
        stats_map[(name, number)] = s
    
    # Merge data
    final_players = []
    
    for player in roster:
        name = player['name']
        number = player['number']
        
        # Find stats
        stats = stats_map.get((name, number), {})
        
        # Map position
        if 'Goalkeeper' in player['position']:
            pos_code = 'GK'
        elif 'Defender' in player['position']:
            pos_code = 'DEF'
        elif 'Midfielder' in player['position']:
            pos_code = 'MID'
        else:
            pos_code = 'FWD'
        
        # Get nationality from flag if available
        national = '-'
        
        final_player = {
            "number": stats.get('number', number) if stats.get('number') else number,
            "name": name,
            "national": national,
            "position": pos_code,
            "age": stats.get('age', player.get('age', '-') if 'age' in player else '-'),
            "apps": stats.get('apps', '-'),
            "min": stats.get('min', '-'),
            "goal": stats.get('goal', '-'),
            "assist": stats.get('assist', '-'),
            "yellow_card": stats.get('yellow_card', '-'),
            "red_card": stats.get('red_card', '-'),
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
        
        final_players.append(final_player)
    
    # Sort by minutes played (desc)
    final_players.sort(key=lambda x: int(x['min']) if x['min'].isdigit() else 0, reverse=True)
    
    return final_players


def main():
    print("=== Creating Full Strasbourg Squad JSON ===\n")
    
    # Extract stats using Chromium
    stats_data = extract_strasbourg_stats()
    
    if not stats_data:
        print("❌ Failed to extract stats")
        return
    
    # Create final JSON
    final_players = create_full_json(stats_data)
    
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
        "players": final_players
    }
    
    output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    with_stats = sum(1 for p in final_players if p['apps'] != "-")
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"Team: Strasbourg")
    print(f"Players: {len(final_players)}")
    print(f"With stats: {with_stats}/{len(final_players)}")
    print(f"Saved to: {output_file}")
    
    # Show top 5
    print(f"\n🏆 Top 5 players by minutes:")
    for p in final_players[:5]:
        print(f"  {p['number']}. {p['name']} | {p['position']} | {p['min']} min | {p['goal']} G | {p['assist']} A")


if __name__ == "__main__":
    main()
