#!/usr/bin/env python3
"""
Final extraction - get ALL players from ALL sections, then dedup
Strasbourg squad has sections: GK, DEF, MID, FWD
Each section contains players for that position, stats are TOTAL (all tournaments)
"""

import json
from playwright.sync_api import sync_playwright
import re

def extract_all_sections_dedup():
    """Extract from ALL sections, dedup by name+number"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players_by_key = {}  # Use dict to auto-dedup
    
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
        
        # Get ALL lineup tables (one per section: GK, DEF, MID, FWD)
        all_tables = page.query_selector_all(".lineupTable")
        print(f"Found {len(all_tables)} sections\n")
        
        for table_idx, table in enumerate(all_tables):
            # Get section title
            title = table.query_selector(".lineupTable__title")
            section_name = title.text_content().strip() if title else f"Section {table_idx}"
            
            # Skip Coach sections
            if 'coach' in section_name.lower():
                continue
            
            print(f"Processing: {section_name}")
            
            # Get rows in this section
            rows = table.query_selector_all(".lineupTable__row")
            
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 9:
                    continue
                
                try:
                    number = cells[0].text_content().strip() if cells[0] else ""
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
                    # Clean name (remove injury text)
                    name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                    
                    age = cells[2].text_content().strip() if len(cells) > 2 and cells[2] else ""
                    apps = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else ""  # Games Played!
                    minutes = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else ""
                    goals = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else ""
                    assists = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else ""
                    yellow = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else ""
                    red = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else ""
                    
                    # Create dedup key
                    key = f"{name}:{number}"
                    
                    # Only add if not seen before (first occurrence wins)
                    if key not in players_by_key:
                        players_by_key[key] = {
                            "number": number if number else "-",
                            "name": name,
                            "national": "-",
                            "position": section_name,  # Will normalize later
                            "age": age if age else "-",
                            "apps": apps if apps else "-",
                            "min": minutes if minutes else "-",
                            "goal": goals if goals else "-",
                            "assist": assists if assists else "-",
                            "yellow_card": yellow if yellow else "-",
                            "red_card": red if red else "-"
                        }
                        
                        # Clean for display
                        clean_name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                        print(f"  ✅ {number}. {clean_name} | Age: {age} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                    continue
    
    return list(players_by_key.values())


def normalize_data(players):
    """Normalize positions and sort"""
    
    # Map section names to codes
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
        section = player['position']
        player['position'] = position_map.get(section, section[:3].upper() if section else '-')
    
    # Sort by minutes (desc)
    players.sort(key=lambda x: int(x['min']) if x['min'].isdigit() else 0, reverse=True)
    
    return players


def main():
    print("=== FINAL EXTRACTION - Strasbourg (All Sections, Deduped) ===\n")
    
    # Extract
    players = extract_all_sections_dedup()
    
    if not players:
        print("❌ No players extracted")
        return
    
    print(f"\n✅ Extracted {len(players)} UNIQUE players (after dedup)\n")
    
    # Normalize
    players = normalize_data(players)
    
    # Enrich with positions from roster
    import glob
    roster_files = glob.glob('/home/openclaw/.openclaw/media/inbound/strasbourg_squad---*.json')
    
    if roster_files:
        print(f"🔍 Enriching with positions from roster...")
        with open(roster_files[0], 'r', encoding='utf-8') as f:
            roster = json.load(f)
        
        roster_map = {}
        for p in roster:
            key = f"{p['name']}:{p.get('number', '')}"
            roster_map[key] = p.get('position', '')
        
        # Update positions
        for player in players:
            key = f"{player['name']}:{player.get('number', '')}"
            if key in roster_map:
                roster_pos = roster_map[key]
                if 'Goalkeeper' in roster_pos:
                    player['position'] = 'GK'
                elif 'Defender' in roster_pos:
                    player['position'] = 'DEF'
                elif 'Midfielder' in roster_pos:
                    player['position'] = 'MID'
                else:
                    player['position'] = 'FWD'
    
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
        "last_updated": "2026-05-13T01:35:00Z"
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
