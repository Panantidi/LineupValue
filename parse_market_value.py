#!/usr/bin/env python3
"""
Parse Market Value for Strasbourg players from Soccerway
"""

import json
import re
import glob
from playwright.sync_api import sync_playwright

def get_profile_path(player_name):
    """Convert player name to Soccerway profile path"""
    # Example: "Bajic Stefan" → "bajic-stefan"
    name_slug = player_name.lower().replace(' ', '-')
    return name_slug

def parse_market_value_from_profile(player_url):
    """Extract market value from player profile page"""
    market_value = "–"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            page.goto(player_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            
            # Look for "Market value:" text
            content = page.content()
            
            # Pattern: "Market value: €X.XXm" or "Market value: €Xm" or "Market value: -"
            patterns = [
                r'Market value:\s*(€[0-9.]+m?)',
                r'Market value:\s*([0-9.]+m?)',
                r'Market value:\s*([^<]+)<'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    market_value = match.group(1).strip()
                    break
            
            browser.close()
            
    except Exception as e:
        print(f"  Error parsing {player_url}: {e}")
    
    return market_value

def main():
    print("=== Parsing Market Values for Strasbourg ===\n")
    
    # Load Strasbourg data
    team_files = glob.glob('/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_*.json')
    if not team_files:
        print("❌ No Strasbourg team file found!")
        return
    
    team_file = team_files[0]
    print(f"Loading: {team_file}\n")
    
    with open(team_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    players = data.get('players', [])
    print(f"Total players: {len(players)}\n")
    
    parsed_count = 0
    errors = 0
    
    for i, player in enumerate(players):
        player_name = player.get('name', '')
        player_number = player.get('number', '')
        
        # Skip if already has market value
        current_mv = player.get('market_value', '').strip()
        if current_mv in ['–', '-', '', 'none', 'None', 'NONE']:
            # Continue to parse
            pass
        else:
            print(f"  {i+1}. {player_number}. {player_name} - {current_mv} (SKIPPED)")
            continue
        
        # Build profile URL
        profile_path = get_profile_path(player_name)
        player_url = f"https://us.soccerway.com/player/{profile_path}/"
        
        print(f"  {i+1}. {player_number}. {player_name}")
        print(f"     URL: {player_url}")
        
        market_value = parse_market_value_from_profile(player_url)
        
        if market_value and market_value != "–":
            player['market_value'] = market_value
            parsed_count += 1
            print(f"     ✅ Market value: {market_value}")
        else:
            print(f"     ⚠️ Market value: NOT FOUND")
            errors += 1
        
        # Small delay to avoid rate limiting
        import time
        time.sleep(0.5)
    
    # Save updated data
    data['last_updated'] = '2026-05-13T03:15:00Z'
    
    output_file = team_file.replace('lineup_ai_', 'lineup_ai_mv_')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"✅ DONE!")
    print(f"{'='*60}")
    print(f"Parsed: {parsed_count}/{len(players)}")
    print(f"Errors: {errors}")
    print(f"Saved to: {output_file}")
    
    # Show sample
    print(f"\n📊 Sample (first 5 with market value):")
    for p in data['players'][:5]:
        if p.get('market_value') and p.get('market_value') != '–':
            print(f"  {p['number']}. {p['name']} - {p['market_value']}")

if __name__ == "__main__":
    main()
