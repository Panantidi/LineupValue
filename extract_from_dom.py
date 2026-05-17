#!/usr/bin/env python3
"""
Extract Strasbourg squad by parsing DOM with correct selectors
"""

from playwright.sync_api import sync_playwright
import json
import re

def extract_strasbourg_squad():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    players = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = browser.new_page()
        
        print("Loading page...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for JS to render
        page.wait_for_timeout(8000)
        
        # Get full page content
        html = page.content()
        
        # Extract player names
        print("Finding players...")
        name_selectors = [
            r'<a[^>]+href="[^"]*player[^"]*"[^>]*>([^<]+)</a>',
            r'class="[^"]*lineupTable__cell--name[^"]*"[^>]*>([^<]+)</a>',
        ]
        
        all_names = set()
        for selector in name_selectors:
            matches = re.findall(selector, html, re.IGNORECASE)
            for match in matches:
                name = match.strip()
                if name and len(name) > 2 and name not in ['Name', 'Position', 'Age', 'Apps', 'G', 'A', 'YC', 'RC']:
                    all_names.add(name)
        
        print(f"Found {len(all_names)} unique player names")
        
        # Now try to get stats by finding rows with numbers
        # Look for pattern: number + name
        number_name_pattern = r'(\d+)\s*.*?<a[^>]+href="[^"]*player[^"]*"[^>]*>([^<]+)</a>'
        
        player_data = []
        matches = re.findall(number_name_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for number, name in matches:
            if number and name:
                number = number.strip()
                name = name.strip()
                
                # Now try to find stats for this player
                # Look for pattern after the name link
                name_in_html = re.escape(name)
                pattern = rf'{name_in_html}[^"\'\n]*?(\d+)[^"\'\n]*?(?:Apps?|G|A|YC|RC)[^"\'\n]*?(\d+)[^"\'\n]*?(?:G)\s*(\d+)[^"\'\n]*?(?:A)\s*(\d+)[^"\'\n]*?(?:YC)\s*(\d+)[^"\'\n]*?(?:RC)\s*(\d+)'
                
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    apps = match.group(1) or "-"
                    goals = match.group(2) or "-"
                    assists = match.group(3) or "-"
                    yellow = match.group(4) or "-"
                    red = match.group(5) or "-"
                    
                    player = {
                        "number": number,
                        "name": name,
                        "national": "-",
                        "position": "-",
                        "age": "-",
                        "apps": apps,
                        "min": "-",
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
                    player_data.append(player)
        
        browser.close()
    
    return player_data


if __name__ == "__main__":
    print("=== Extracting Strasbourg via DOM parsing ===\n")
    
    players = extract_strasbourg_squad()
    
    print(f"\nFound {len(players)} players with stats")
    
    if players:
        # Print sample
        print("\nSample:")
        for p in players[:3]:
            print(f"  {p['number']}. {p['name']} - Apps: {p['apps']}, G: {p['goal']}, A: {p['assist']}")
        
        # Create JSON
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
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved to: {output_file}")
    else:
        print("❌ No players found")
