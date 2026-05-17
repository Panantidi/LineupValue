#!/usr/bin/env python3
"""
Final extraction - extract ONLY from TOTAL sections
Strategy: Soccerway shows multiple tables (per tournament), find TOTAL and use that
"""

import json
import re
import os
from playwright.sync_api import sync_playwright

def extract_total_only():
    """Extract ONLY from TOTAL sections"""
    
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
        page.wait_for_timeout(10000)
        
        # Get ALL lineup tables
        all_tables = page.query_selector_all(".lineupTable")
        print(f"Found {len(all_tables)} sections\n")
        
        # Process each section
        for table_idx, table in enumerate(all_tables):
            title = table.query_selector(".lineupTable__title")
            section_name = title.text_content().strip() if title else f"Section {table_idx}"
            
            # Skip Coach sections
            if 'coach' in section_name.lower():
                continue
            
            # Check if this is TOTAL section (highest apps)
            rows = table.query_selector_all(".lineupTable__row")
            
            if not rows:
                continue
            
            # Get max apps for this section to determine if TOTAL
            max_apps_in_section = 0
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                if len(cells) > 3:
                    apps = cells[3].text_content().strip()
                    if apps.isdigit():
                        max_apps_in_section = max(max_apps_in_section, int(apps))
            
            # If section has players with high apps (like Penders 50), assume it's TOTAL
            if max_apps_in_section >= 30:  # Threshold
                print(f"🎯 Processing TOTAL section: {section_name} (max apps: {max_apps_in_section})")
            else:
                print(f"  Skipping partial section: {section_name} (max apps: {max_apps_in_section})")
                continue
            
            # Extract players from this TOTAL section
            for row in rows:
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 9:
                    continue
                
                try:
                    number = cells[0].text_content().strip() if cells[0] else ""
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
                    # Clean name
                    name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                    
                    age = cells[2].text_content().strip() if len(cells) > 2 and cells[2] else ""
                    apps = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else ""
                    minutes = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else ""
                    goals = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else ""
                    assists = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else ""
                    yellow = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else ""
                    red = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else ""
                    
                    # Create key for dedup
                    key = f"{name}:{number}"
                    
                    # Always use first occurrence (TOTAL section)
                    players_by_key[key] = {
                        "number": number if number else "-",
                        "name": name,
                        "national": "-",
                        "position": section_name,
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
                    
                    # Display
                    clean_name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
                    print(f"  ✅ {number}. {clean_name} | Age: {age} | Apps: {apps} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                    continue
    
    return list(players_by_key.values())


def normalize_data(players):
    """Normalize positions and sort"""
    
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
    
    # Sort by apps (desc)
    players.sort(key=lambda x: int(x['apps']) if x['apps'].isdigit() else 0, reverse=True)
    
    return players


def enrich_data(players, roster_path):
    """Enrich with nationalities from roster"""
    
    if not os.path.exists(roster_path):
        return players
    
    with open(roster_path, 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    roster_map = {}
    for p in roster:
        key = f"{p['name']}:{p.get('number', '')}"
        roster_map[key] = p.get('national', '-')
    
    for player in players:
        key = f"{player['name']}:{player.get('number', '')}"
        if key in roster_map:
            player['national'] = roster_map[key]
    
    return players


def main():
    print("=== FINAL EXTRACTION - TOTAL SECTION ONLY ===\n")
    
    # Extract from TOTAL sections only
    players = extract_total_only()
    
    if not players:
        print("❌ No players extracted from TOTAL sections")
        return
    
    print(f"\n✅ Extracted {len(players)} players from TOTAL sections\n")
    
    # Normalize
    players = normalize_data(players)
    
    # Enrich with nationalities
    import glob
    roster_files = glob.glob('/home/openclaw/.openclaw/media/inbound/strasbourg_squad---*.json')
    
    if roster_files:
        print(f"🔍 Enriching with nationalities...")
        players = enrich_data(players, roster_files[0])
    
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
        "last_updated": "2026-05-13T01:50:00Z"
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
    print(f"\n🏆 TOP 10 PLAYERS (by Apps - TOTAL season):")
    for p in players[:10]:
        print(f"  {p['number']}. {p['name']} | {p['position']} | {p['apps']} apps | {p['min']} min | {p['goal']} G | {p['assist']} A")


if __name__ == "__main__":
    main()
