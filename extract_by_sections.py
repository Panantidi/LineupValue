#!/usr/bin/env python3
"""
Extract players BY SECTIONS (Goalkeepers/Defenders/Midfielders/Forwards)
This bypasses the lazy loading issue!
"""

import json
from playwright.sync_api import sync_playwright

def extract_by_sections():
    """Extract ALL players by section"""
    
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    all_players = []
    current_section = None
    
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
        
        # Wait for initial render
        page.wait_for_timeout(8000)
        
        # Find ALL sections (Goalkeepers, Defenders, etc.)
        sections = page.query_selector_all(".lineupTable")
        print(f"Found {len(sections)} lineupTable sections")
        
        for section_idx, section in enumerate(sections):
            # Get section title
            title_elem = section.query_selector(".lineupTable__title")
            section_name = title_elem.text_content().strip() if title_elem else f"Section {section_idx}"
            
            print(f"\n{'='*60}")
            print(f"SECTION: {section_name}")
            print(f"{'='*60}")
            
            # Get rows in this section
            rows = section.query_selector_all(".lineupTable__row")
            print(f"Found {len(rows)} players in this section")
            
            current_section = section_name
            
            for row_idx, row in enumerate(rows):
                cells = row.query_selector_all(".lineupTable__cell")
                
                if len(cells) < 9:
                    continue
                
                try:
                    number = cells[0].text_content().strip() if cells[0] else ""
                    name = cells[1].text_content().strip() if cells[1] else ""
                    
                    if not name or name in ['Name', 'Number', 'Position', 'Age']:
                        continue
                    
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
                        "position": current_section,
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
                    
                    all_players.append(player)
                    
                    # Show first few from each section
                    if row_idx < 3:
                        print(f"  ✅ {number}. {name} | Age: {age} | Min: {minutes} | G: {goals} | A: {assists}")
                
                except Exception as e:
                    print(f"  ⚠️ Error in row {row_idx}: {e}")
                    continue
        
        browser.close()
    
    return all_players


def main():
    print("=== Extracting Strasbourg by SECTIONS ===\n")
    
    players = extract_by_sections()
    
    if players:
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS!")
        print(f"{'='*60}")
        print(f"Total players: {len(players)}")
        
        # Count by section
        sections = {}
        for p in players:
            sec = p['position']
            sections[sec] = sections.get(sec, 0) + 1
        
        print(f"\nBy section:")
        for sec, count in sections.items():
            print(f"  {sec}: {count}")
        
        # Normalize positions
        for p in players:
            if 'Goalkeeper' in p['position']:
                p['position'] = 'GK'
            elif 'Defender' in p['position']:
                p['position'] = 'DEF'
            elif 'Midfielder' in p['position']:
                p['position'] = 'MID'
            elif 'Forward' in p['position']:
                p['position'] = 'FWD'
        
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
            "players": players
        }
        
        # Save
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        with_stats = sum(1 for p in players if p['min'] != "-")
        
        print(f"\n✅ Saved to: {output_file}")
        print(f"✅ Players with stats: {with_stats}/{len(players)}")
        
        # Show top 10
        print(f"\n🏆 TOP 10 PLAYERS:")
        for p in players[:10]:
            print(f"  {p['number']}. {p['name']} | {p['position']} | {p['min']} min | {p['goal']} G | {p['assist']} A | YC: {p['yellow_card']}")
    
    else:
        print("❌ No players extracted")


if __name__ == "__main__":
    main()
