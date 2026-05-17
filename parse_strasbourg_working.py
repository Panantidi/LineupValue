#!/usr/bin/env python3
"""
Extract Strasbourg squad using YOUR working Playwright method
Selectors from your successful extraction:
- .lineupTable__row - player rows
- .lineupTable__cell--jersey - jersey number
- .lineupTable__cell--name - player name
"""

from playwright.sync_api import sync_playwright
import json

def extract_strasbourg_squad():
    """Extract Strasbourg squad using your proven selectors"""
    
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
        
        # Wait for JS to render the squad table
        print("Waiting for squad to render...")
        page.wait_for_timeout(10000)
        
        # Find lineup table
        print("Finding lineup table...")
        lineup_table = page.query_selector("div.lineupTable")
        
        if not lineup_table:
            print("❌ No lineup table found")
            browser.close()
            return None
        
        # Get all player rows
        rows = lineup_table.query_selector_all(".lineupTable__row")
        print(f"Found {len(rows)} player rows")
        
        if len(rows) == 0:
            print("❌ No player rows found")
            browser.close()
            return None
        
        # Track current position section
        current_position = None
        
        for row in rows:
            # Check if this is a position header row
            if row.query_selector("th"):
                th_text = row.query_selector("th").text_content().strip().lower()
                if "goalkeeper" in th_text:
                    current_position = "GK"
                elif "defender" in th_text:
                    current_position = "DEF"
                elif "midfielder" in th_text:
                    current_position = "MID"
                elif "forward" in th_text:
                    current_position = "FWD"
                continue
            
            # Extract player data
            cells = row.query_selector_all(".lineupTable__cell")
            
            if len(cells) < 8:
                continue
            
            try:
                # Jersey number
                jersey = row.query_selector(".lineupTable__cell--jersey")
                number = jersey.text_content().strip() if jersey else "-"
                
                # Player name
                name_link = row.query_selector(".lineupTable__cell--name a")
                name = name_link.text_content().strip() if name_link else row.query_selector(".lineupTable__cell--name").text_content().strip()
                
                # Nationality (usually flag image with alt text or text next to flag)
                nat_cell = cells[2] if len(cells) > 2 else None
                nationality = "-"
                if nat_cell:
                    # Try to get flag alt text
                    flag_img = nat_cell.query_selector("img")
                    if flag_img:
                        nationality = flag_img.get_attribute("alt") or nat_cell.text_content().strip()
                    else:
                        nationality = nat_cell.text_content().strip()
                
                # Position from header or cell
                position = current_position or "-"
                if cells[3]:
                    pos_text = cells[3].text_content().strip().upper()[:3]
                    if pos_text in ["GK", "DEF", "MID", "FWD"]:
                        position = pos_text
                
                # Age
                age = "-"
                if cells[4]:
                    age_text = cells[4].text_content().strip()
                    if age_text and age_text.isdigit():
                        age = age_text
                
                # Apps
                apps = "-"
                if cells[5]:
                    apps = cells[5].text_content().strip()
                
                # Minutes
                minutes = "-"
                if cells[6]:
                    minutes = cells[6].text_content().strip()
                
                # Goals
                goals = "-"
                if cells[7]:
                    goals = cells[7].text_content().strip()
                
                # Assists
                assists = "-"
                if len(cells) > 8 and cells[8]:
                    assists = cells[8].text_content().strip()
                
                # Yellow cards
                yellow_cards = "-"
                if len(cells) > 9 and cells[9]:
                    yellow_cards = cells[9].text_content().strip()
                
                # Red cards
                red_cards = "-"
                if len(cells) > 10 and cells[10]:
                    red_cards = cells[10].text_content().strip()
                
                player = {
                    "number": number,
                    "name": name,
                    "national": nationality,
                    "position": position,
                    "age": age,
                    "apps": apps,
                    "min": minutes,
                    "goal": goals,
                    "assist": assists,
                    "yellow_card": yellow_cards,
                    "red_card": red_cards,
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
                print(f"  ✅ {number}. {name} | {nationality} | {position} | Age: {age} | Apps: {apps} | G: {goals} | A: {assists}")
                
            except Exception as e:
                print(f"  ⚠️ Error parsing row: {e}")
                continue
        
        browser.close()
    
    return players


def main():
    print("=== Extracting Strasbourg Squad (Your Working Method) ===\n")
    
    players = extract_strasbourg_squad()
    
    if players:
        print(f"\n✅ Successfully extracted {len(players)} players")
        
        # Deduplicate by name (your note mentioned 218 records with duplicates)
        seen_names = set()
        unique_players = []
        for p in players:
            key = (p['name'], p['number'])
            if key not in seen_names:
                seen_names.add(key)
                unique_players.append(p)
        
        if len(unique_players) < len(players):
            print(f"   (deduplicated from {len(players)} to {len(unique_players)} players)")
        
        # Save to JSON
        team_data = {
            "team": {
                "id": "nP6UzIU1",
                "name": "Strasbourg",
                "slug": "strasbourg",
                "league": "Ligue 1",
                "country": "France"
            },
            "matches": [],
            "players": unique_players
        }
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved to: {output_file}")
        
        # Show summary
        print(f"\n=== Squad Summary ===")
        print(f"Total: {len(unique_players)} players")
        
        gk = sum(1 for p in unique_players if p['position'] == 'GK')
        df = sum(1 for p in unique_players if p['position'] == 'DEF')
        mf = sum(1 for p in unique_players if p['position'] == 'MID')
        fw = sum(1 for p in unique_players if p['position'] == 'FWD')
        
        print(f"  GK:  {gk}")
        print(f"  DEF: {df}")
        print(f"  MID: {mf}")
        print(f"  FWD: {fw}")
        
        # Show top scorers
        goal_scorers = [p for p in unique_players if p['goal'] and p['goal'].isdigit() and int(p['goal']) > 0]
        if goal_scorers:
            goal_scorers.sort(key=lambda x: int(x['goal']), reverse=True)
            print(f"\nTop scorers:")
            for p in goal_scorers[:3]:
                print(f"  {p['number']}. {p['name']} - {p['goal']} goals")
        
    else:
        print("❌ No data extracted")


if __name__ == "__main__":
    main()
