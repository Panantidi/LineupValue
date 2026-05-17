#!/usr/bin/env python3
"""
Extract ONLY TOTAL stats (summed across all tournaments)
Strategy:
1. Find the TOTAL section (not individual tournament sections)
2. Extract players from that section only
3. Deduplicate
"""

import json
from playwright.sync_api import sync_playwright
import re

def extract_total_stats():
    """Extract ONLY from TOTAL section"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    seen_names = set()  # Dedup
    
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
        
        # Get ALL lineup tables
        all_tables = page.query_selector_all(".lineupTable")
        print(f"Found {len(all_tables)} total tables")
        
        # Look for TOTAL section
        total_table = None
        total_title = None
        
        for table in all_tables:
            title = table.query_selector(".lineupTable__title")
            if title:
                title_text = title.text_content().strip().lower()
                print(f"Checking: '{title_text}'")
                
                if 'total' in title_text:
                    total_table = table
                    total_title = title_text
                    print(f"✅ Found TOTAL section: {total_title}")
                    break
        
        if not total_table:
            print("❌ No TOTAL section found, using last/main table")
            # Fallback: use the last table or first with players
            for table in all_tables:
                rows = table.query_selector_all(".lineupTable__row")
                if rows and len(rows) > 5:  # If it has players
                    total_table = table
                    break
        
        if total_table:
            # Get all rows from TOTAL table
            rows = total_table.query_selector_all(".lineupTable__row")
            print(f"\nExtracting from TOTAL section: {len(rows)} players\n")
            
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 9:
                    continue
                
                try:
                    number = cells[0].text_content().strip() if cells[0] else ""
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
                    # Dedup
                    key = (name, number)
                    if key in seen_names:
                        print(f"  ⚠️ Duplicate: {name} ({number})")
                        continue
                    
                    seen_names.add(key)
                    
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
                        "national": "-",
                        "position": "-",
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
                    
                    players.append(player)
                    
                    # Clean name for display
                    clean_name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                    print(f"  ✅ {number}. {clean_name} | Age: {age} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                    continue
        else:
            print("❌ No valid table found")
        
        browser.close()
    
    return players


def enrich_positions(players, roster_path):
    """Enrich with positions from roster JSON"""
    
    if not os.path.exists(roster_path):
        print(f"⚠️ Roster not found: {roster_path}")
        return players
    
    with open(roster_path, 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    position_map = {}
    for p in roster:
        key = (p['name'], p.get('number', ''))
        
        if 'Goalkeeper' in p['position']:
            pos = 'GK'
        elif 'Defender' in p['position']:
            pos = 'DEF'
        elif 'Midfielder' in p['position']:
            pos = 'MID'
        else:
            pos = 'FWD'
        
        position_map[key] = pos
    
    for player in players:
        key = (player['name'], player.get('number', ''))
        if key in position_map:
            player['position'] = position_map[key]
    
    return players


def main():
    import os
    
    print("=== Extracting TOTAL Stats Only (Strasbourg) ===\n")
    
    # Extract from TOTAL section
    players = extract_total_stats()
    
    if not players:
        print("❌ No players extracted")
        return
    
    print(f"\n✅ Extracted {len(players)} unique players from TOTAL section")
    
    # Enrich with positions from your roster
    import glob
    roster_files = glob.glob('/home/openclaw/.openclaw/media/inbound/strasbourg_squad---*.json')
    
    if roster_files:
        print(f"🔍 Enriching with positions from: {roster_files[0]}")
        players = enrich_positions(players, roster_files[0])
    
    # Sort by minutes
    players.sort(key=lambda x: int(x['min']) if x['min'].isdigit() else 0, reverse=True)
    
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
        "last_updated": "2026-05-13T01:30:00Z"
    }
    
    # Save
    output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    with_stats = sum(1 for p in players if p['min'] != "-")
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"Team: Strasbourg")
    print(f"Players: {len(players)}")
    print(f"With stats: {with_stats}/{len(players)}")
    print(f"Saved to: {output_file}")
    
    # Show top 10
    print(f"\n🏆 TOP 10 PLAYERS (by minutes):")
    for p in players[:10]:
        print(f"  {p['number']}. {p['name']} | {p['position']} | {p['min']} min | {p['goal']} G | {p['assist']} A | YC: {p['yellow_card']}")


if __name__ == "__main__":
    main()
