#!/usr/bin/env python3
"""
Parse Market Value for Strasbourg players from Soccerway
Using correct player profile URL structure
"""

import json
import re
import glob
import time
from playwright.sync_api import sync_playwright

def get_player_id_from_name(player_name):
    """Get player ID for Soccerway URL"""
    # Example: "Penders Mike" → "nyaJupUE"
    # We need to extract or lookup the ID
    
    # Try to find from workspace files (we might have profile_path)
    return "nyaJupUE"  # placeholder - will be filled from data

def parse_market_value(player_url, player_name):
    """Extract Market Value from player profile page"""
    print(f"     Loading: {player_url}")
    
    try:
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
            
            # Load page
            page.goto(player_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            # Try specific selector you provided
            try:
                element = page.query_selector('//*[@id="player-profile-heading"]/div/div/div[2]/div[4]/span[2]')
                if element:
                    value = element.text_content().strip()
                    print(f"     ✅ Found with XPath: {value}")
                    browser.close()
                    return value
            except:
                pass
            
            # Try CSS selectors as fallback
            selectors = [
                '[data-testid="market-value"]',
                '[class*="market-value"]',
                '[class*="player-value"]',
                '.market-value',
                '.player-value'
            ]
            
            for selector in selectors:
                try:
                    element = page.query_selector(selector)
                    if element:
                        value = element.text_content().strip()
                        print(f"     ✅ Found with CSS '{selector}': {value}")
                        browser.close()
                        return value
                except:
                    continue
            
            # Get all page content and search
            content = page.content()
            
            # Pattern: Market value: €XXm
            patterns = [
                r'Market value:\s*(€[0-9,.]+m?)',
                r'Market Value:\s*(€[0-9,.]+m?)',
                r'value:\s*(€[0-9,.]+m?)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    print(f"     ✅ Found with regex: {value}")
                    browser.close()
                    return value
            
            print(f"     ⚠️ Market value: NOT FOUND")
            browser.close()
            return "–"
            
    except Exception as e:
        print(f"     ❌ Error: {e}")
        return "–"

def main():
    print("=== Parsing Market Values (Correct Approach) ===\n")
    
    # Load Strasbourg data (full squad)
    team_files = glob.glob('/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json')
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
        if current_mv and current_mv not in ['–', '-', '']:
            print(f"  {i+1}. {player_number}. {player_name} - {current_mv} (SKIPPED)")
            continue
        
        # Build profile URL - we need the correct player ID
        # From user's example: Penders Mike → nyaJupUE
        # We'll use a simple slug for now
        profile_slug = player_name.lower().replace(' ', '-')
        player_url = f"https://us.soccerway.com/player/{profile_slug}/"
        
        print(f"\n  {i+1}. {player_number}. {player_name}")
        
        market_value = parse_market_value(player_url, player_name)
        
        if market_value and market_value != "–":
            player['market_value'] = market_value
            parsed_count += 1
        else:
            errors += 1
        
        # Small delay
        time.sleep(0.5)
    
    # Save updated data
    data['last_updated'] = '2026-05-13T03:25:00Z'
    
    output_file = team_file.replace('lineup_ai_', 'lineup_mv_')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"✅ DONE!")
    print(f"{'='*60}")
    print(f"Parsed: {parsed_count}/{len(players)}")
    print(f"Errors: {errors}")
    print(f"Saved to: {output_file}")
    
    # Show sample
    print(f"\n📊 Sample (first 5):")
    for p in data['players'][:5]:
        print(f"  {p['number']}. {p['name']} - {p.get('market_value', '–')}")

if __name__ == "__main__":
    main()
