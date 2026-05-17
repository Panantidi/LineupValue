#!/usr/bin/env python3
"""
Parse Strasbourg squad from Soccerway by extracting HTML and parsing it
This approach works when Playwright can't access the rendered DOM
"""

import json
import re

def parse_squad_from_html(html_file):
    """Parse squad data from previously saved HTML"""
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    players = []
    
    # Find all player entries - they are usually in table rows
    # Look for patterns like:
    # <tr>...<td><a href="/player/...">Name</a></td>...
    
    # Find all rows that contain player links
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    
    for row in rows:
        # Check if this row contains player data (has jersey number)
        if not re.search(r'\b\d{1,3}\b', row):
            continue
        
        # Extract number
        number_match = re.search(r'<td[^>]*>\s*(\d{1,3})\s*</td>', row)
        if not number_match:
            continue
        number = number_match.group(1)
        
        # Extract name (from link)
        name_match = re.search(r'<a[^>]+href="[^"]*player[^"]*"[^>]*>([^<]+)</a>', row)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        
        # Skip if it's a header or team name
        if len(name) < 3 or name in ['Name', 'Number', 'Position', 'Age', 'Apps', 'G', 'A', 'YC', 'RC', 'Min']:
            continue
        
        # Extract nationality (usually next cell after name or flag image)
        nat_match = re.search(r'<td[^>]*>([^<]+)(?:</td>)?', row)
        nationality = "France" if nat_match and len(nat_match.groups()) > 0 and nat_match.group(1) else "-"
        
        # Extract position
        pos_match = re.search(r'<td[^>]*>(?:Defender|Midfielder|Forward|Goalkeeper|GK|DEF|MID|FWD)[^<]*</td>', row, re.IGNORECASE)
        position = pos_match.group(0) if pos_match else "-"
        
        # Extract stats - look for pattern after player info
        # This is tricky because stats might be in different order
        apps_match = re.search(r'Apps?\s*(\d+)', row, re.IGNORECASE)
        goals_match = re.search(r'\bG\s*(\d+)', row)
        assists_match = re.search(r'\bA\s*(\d+)', row)
        yellow_match = re.search(r'\bYC\s*(\d+)', row)
        red_match = re.search(r'\bRC\s*(\d+)', row)
        minutes_match = re.search(r'Min(?:utes?)?\s*(\d+)', row, re.IGNORECASE)
        age_match = re.search(r'<td[^>]*\b(\d{1,2})\b[^>]*>[\s\n]*</td>', row)
        
        player = {
            "number": number,
            "name": name,
            "national": nationality,
            "position": position,
            "age": age_match.group(1) if age_match else "-",
            "apps": apps_match.group(1) if apps_match else "-",
            "min": minutes_match.group(1) if minutes_match else "-",
            "goal": goals_match.group(1) if goals_match else "-",
            "assist": assists_match.group(1) if assists_match else "-",
            "yellow_card": yellow_match.group(1) if yellow_match else "-",
            "red_card": red_match.group(1) if red_match else "-",
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
        print(f"✅ {number}. {name} | {nationality} | {position} | Apps: {player['apps']}, G: {player['goal']}, A: {player['assist']}")
    
    return players


if __name__ == "__main__":
    print("=== Parsing Strasbourg from HTML file ===\n")
    
    # Try different HTML files
    html_files = [
        '/tmp/strasbourg_debug.html',
        '/tmp/strasbourg_extract.log',
    ]
    
    for html_file in html_files:
        try:
            print(f"Trying: {html_file}")
            players = parse_squad_from_html(html_file)
            
            if players:
                print(f"\n✅ Extracted {len(players)} players")
                
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
                
                print(f"✅ Saved to: {output_file}")
                break
            else:
                print("❌ No players found")
        except Exception as e:
            print(f"❌ Error: {e}")
