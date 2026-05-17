#!/usr/bin/env python3
"""
Extract team squad from Soccerway
Usage: python extract_team_squad.py [team_id]

This script expects you to manually extract the HTML or use your working method.
Then run this to parse and convert to LineUp AI format.
"""

import json
import re
import sys
import os

def parse_player_data(html_content):
    """Parse player data from Soccerway HTML"""
    
    players = []
    
    # Find all player rows - look for pattern with player links
    # Common patterns in Soccerway:
    # <tr><td>1</td><td><a href="/player/...">Name</a></td><td>Flag</td><td>Pos</td><td>Age</td>...</tr>
    
    # Find all tables
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html_content, re.DOTALL | re.IGNORECASE)
    
    for table_idx, table in enumerate(tables):
        # Find rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL | re.IGNORECASE)
        
        for row_idx, row in enumerate(rows):
            # Skip if no cells
            if '<td' not in row:
                continue
            
            # Extract cells
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            
            if len(cells) < 8:
                continue
            
            # Try to identify if this is a player row
            # Look for player name in a link
            name_match = re.search(r'<a[^>]+href="[^"]*/player/[^"]*"[^>]*>([^<]+)</a>', row)
            
            if not name_match:
                continue
            
            name = name_match.group(1).strip()
            
            # Skip if it looks like a header
            if name in ['Name', 'Player', 'Position', 'Age', 'Apps']:
                continue
            
            # Extract number (jersey number is usually first cell with a digit)
            number = "-"
            for cell in cells[:2]:
                cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                if cell_text.isdigit() and len(cell_text) <= 3:
                    number = cell_text
                    break
            
            # Extract nationality
            nationality = "-"
            # Look for flag image or alt text
            nat_match = re.search(r'alt="([^"]+)"', row)
            if nat_match:
                nationality = nat_match.group(1).strip()
            
            # Try to find position (GK, DEF, MID, FWD or full names)
            position = "-"
            pos_keywords = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward', 'GK', 'DEF', 'MID', 'FWD']
            for keyword in pos_keywords:
                if keyword.lower() in row.lower():
                    position = keyword
                    break
            
            # Extract stats - this is tricky because layout varies
            # Look for patterns like "Apps 25", "G 5", "A 3", "YC 2", "RC 0", "Min 1800"
            apps = "-"
            min_played = "-"
            goals = "-"
            assists = "-"
            yellow_cards = "-"
            red_cards = "-"
            
            # Try to find "Apps X" pattern
            apps_match = re.search(r'Apps?\s*(\d+)', row, re.IGNORECASE)
            if apps_match:
                apps = apps_match.group(1)
            
            # Try to find "Min" pattern
            min_match = re.search(r'Min(?:utes?)?\s*(\d+)', row, re.IGNORECASE)
            if min_match:
                min_played = min_match.group(1)
            
            # Try to find "G" or "Goals" pattern (be careful with position codes)
            g_match = re.search(r'(?<![\w])G\s*(\d+)(?![\w])', row)
            if g_match:
                goals = g_match.group(1)
            
            # Try to find "A" pattern (be careful with position codes)
            a_match = re.search(r'(?<![\w])A\s*(\d+)(?![\w])', row)
            if a_match:
                assists = a_match.group(1)
            
            # Try to find "YC" pattern
            yc_match = re.search(r'YC\s*(\d+)', row)
            if yc_match:
                yellow_cards = yc_match.group(1)
            
            # Try to find "RC" pattern
            rc_match = re.search(r'RC\s*(\d+)', row)
            if rc_match:
                red_cards = rc_match.group(1)
            
            # Extract age if found
            age = "-"
            # Look for 2-digit number after name position (common age range)
            age_match = re.search(r'>(\d{1,2})<', row)
            if age_match:
                age_num = int(age_match.group(1))
                if 14 <= age_num <= 45:  # Reasonable age range
                    age = str(age_num)
            
            player = {
                "number": number,
                "name": name,
                "national": nationality,
                "position": position,
                "age": age,
                "apps": apps,
                "min": min_played,
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
    
    return players


def save_team_data(team_id, team_name, country, league, players):
    """Save team data to JSON file"""
    
    team_data = {
        "team": {
            "id": team_id,
            "name": team_name,
            "slug": team_name.lower().replace(' ', '-'),
            "league": league,
            "country": country
        },
        "matches": [],
        "players": players
    }
    
    output_file = f"/home/openclaw/.openclaw/workspace/lineup_ai_{country.lower()}_{league.replace(' ', '-').lower()}_team_{team_name.lower()}_{team_id}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    return output_file


def main():
    """
    Usage examples:
    
    1. From saved HTML file:
       python extract_team_squad.py --file /path/to/strasbourg.html --id nP6UzIU1 --name Strasbourg --country France --league "Ligue 1"
    
    2. Interactive mode:
       python extract_team_squad.py
    
    This parses HTML that contains player data and converts to LineUp AI format.
    """
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract team squad from Soccerway HTML')
    parser.add_argument('--file', '-f', help='Path to HTML file with player data')
    parser.add_argument('--id', '-i', help='Team ID (e.g., nP6UzIU1)')
    parser.add_argument('--name', '-n', help='Team name (e.g., Strasbourg)')
    parser.add_argument('--country', '-c', help='Country (e.g., France)')
    parser.add_argument('--league', '-l', help='League (e.g., Ligue 1)')
    
    args = parser.parse_args()
    
    # Interactive mode if no arguments
    if not all([args.file, args.id, args.name, args.country, args.league]):
        print("=== Extract Team Squad from Soccerway HTML ===\n")
        print("Please provide all arguments:")
        print("  --file     Path to HTML file")
        print("  --id       Team ID")
        print("  --name     Team name")
        print("  --country  Country")
        print("  --league   League")
        print("\nExample:")
        print("  python extract_team_squad.py --file /tmp/strasbourg.html --id nP6UzIU1 --name Strasbourg --country France --league \"Ligue 1\"")
        return
    
    # Read HTML file
    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        return
    
    print(f"Reading HTML file: {args.file}")
    with open(args.file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    print(f"HTML size: {len(html_content)} chars")
    
    # Parse player data
    print("\nParsing players...")
    players = parse_player_data(html_content)
    
    print(f"Found {len(players)} players")
    
    if not players:
        print("\n⚠️ No players found!")
        print("Try opening the page in browser, then View Source (Ctrl+U) and save the HTML.")
        return
    
    # Show first 5 players
    print("\nSample players:")
    for p in players[:5]:
        print(f"  {p['number']}. {p['name']} | {p['national']} | {p['position']}")
    
    # Save team data
    output_file = save_team_data(
        args.id,
        args.name,
        args.country,
        args.league,
        players
    )
    
    print(f"\n✅ Saved {len(players)} players to: {output_file}")


if __name__ == "__main__":
    main()
