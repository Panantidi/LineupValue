#!/usr/bin/env python3
"""
Extract squad with ALL stats including Apps (Games Played)
Target column: Jersey icon = Apps (Games Played)
"""

import json
import re
from playwright.sync_api import sync_playwright

def extract_with_apps():
    """Extract all players with Apps column"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players_by_key = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1366, 'height': 768}
        )
        
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
        """)
        
        page = context.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for render
        page.wait_for_timeout(10000)
        
        # Get all lineup tables
        all_tables = page.query_selector_all(".lineupTable")
        print(f"Found {len(all_tables)} sections\n")
        
        for table_idx, table in enumerate(all_tables):
            title = table.query_selector(".lineupTable__title")
            section_name = title.text_content().strip() if title else f"Section {table_idx}"
            
            if 'coach' in section_name.lower():
                continue
            
            print(f"Processing: {section_name}")
            
            rows = table.query_selector_all(".lineupTable__row")
            
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 10:  # Need more cells for apps
                    continue
                
                try:
                    # Cell 0: Jersey Number
                    number = cells[0].text_content().strip() if cells[0] else ""
                    
                    # Cell 1: Name (with link)
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
                    # Clean name
                    name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                    
                    # Cell 2: Nationality (flag)
                    # cell_text = cells[2].text_content().strip() if cells[2] else ""
                    
                    # Cell 3: Position
                    position = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else ""
                    
                    # Cell 4: Age
                    age = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else ""
                    
                    # Cell 5: Apps (Games Played) - THIS IS WHAT YOU WANT!
                    apps = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else ""
                    
                    # Cell 6: Minutes
                    minutes = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else ""
                    
                    # Cell 7: Goals
                    goals = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else ""
                    
                    # Cell 8: Assists
                    assists = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else ""
                    
                    # Cell 9: Yellow Cards
                    yellow = cells[9].text_content().strip() if len(cells) > 9 and cells[9] else ""
                    
                    # Cell 10: Red Cards
                    red = cells[10].text_content().strip() if len(cells) > 10 and cells[10] else ""
                    
                    # Create key for dedup
                    key = f"{name}:{number}"
                    
                    if key not in players_by_key:
                        player = {
                            "number": number if number else "-",
                            "name": name,
                            "national": "-",  # Could extract from flag
                            "position": position,
                            "age": age if age else "-",
                            "apps": apps if apps else "-",
                            "min": minutes if minutes else "-",
                            "goal": goals if goals else "-",
                            "assist": assists if assists else "-",
                            "yellow_card": yellow if yellow else "-",
                            "red_card": red if red else "-",
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
                        
                        players_by_key[key] = player
                        
                        # Display
                        clean_name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                        print(f"  ✅ {number}. {clean_name} | Age: {age} | Apps: {apps} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                    continue
    
    return list(players_by_key.values())


def normalize_positions(players):
    """Map section names to codes"""
    
    position_map = {
        'Goalkeepers': 'GK',
        'Defenders': 'DEF',
        'Midfielders': 'MID',
        'Forwards': 'FWD',
        'Goalkeeper': 'GK',
        'Defender': 'DEF',
        'Midfielder': 'MID',
        'Forward': 'FWD'
    }
    
    for player in players:
        pos = player['position']
        player['position'] = position_map.get(pos, pos[:3].upper() if pos else '-')
    
    # Sort by apps (desc)
    players.sort(key=lambda x: int(x['apps']) if x['apps'].isdigit() else 0, reverse=True)
    
    return players


def main():
    print("=== EXTRACTION WITH APPS (Games Played) ===\n")
    
    # Extract
    players = extract_with_apps()
    
    if not players:
        print("❌ No players extracted")
        return
    
    print(f"\n✅ Extracted {len(players)} unique players\n")
    
    # Normalize
    players = normalize_positions(players)
    
    # Enrich with nationalities from roster
    import glob
    roster_files = glob.glob('/home/openclaw/.openclaw/media/inbound/strasbourg_squad---*.json')
    
    if roster_files:
        print(f"🔍 Enriching with nationalities from roster...")
        with open(roster_files[0], 'r', encoding='utf-8') as f:
            roster = json.load(f)
        
        roster_map = {}
        for p in roster:
            key = f"{p['name']}:{p.get('number', '')}"
            roster_map[key] = p.get('national', '-')
        
        for player in players:
            key = f"{player['name']}:{player.get('number', '')}"
            if key in roster_map:
                player['national'] = roster_map[key]
    
    # Create team data
    team_data = {
        "team": {
            "id": "nP6UzIU1",
            "name": "Strasbourg",
            "slug": "strasbourg",
            "league": "Ligue 1",
            "country": "France"
        },
        "matches": [],
        "players": players,
        "last_updated": "2026-05-13T01:40:00Z"
    }
    
    # Save
    output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    with_apps = sum(1 for p in players if p['apps'] != "-")
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"Team: Strasbourg")
    print(f"Players: {len(players)}")
    print(f"With Apps: {with_apps}/{len(players)}")
    print(f"Saved to: {output_file}")
    
    # Show top 10 by apps
    print(f"\n🏆 TOP 10 PLAYERS (by Apps):")
    for p in players[:10]:
        print(f"  {p['number']}. {p['name']} | {p['position']} | {p['apps']} apps | {p['goal']} G | {p['assist']} A | YC: {p['yellow_card']}")


if __name__ == "__main__":
    main()
