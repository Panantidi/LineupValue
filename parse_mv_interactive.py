#!/usr/bin/env python3
"""
Parse Market Value for Strasbourg players using Chromium interactive mode
Switches between views on player profile page
"""

import json
import re
import glob
import time
from playwright.sync_api import sync_playwright

def switch_to_market_value_view(page):
    """Try to switch to Market Value view on player page"""
    print("    Searching for view switchers...")
    
    # Common selectors for view tabs/switches
    selectors = [
        '[class*="tab"]',
        '[class*="nav"]',
        '[class*="section"]',
        '[data-tab]',
        'button[class*="tab"]',
        'a[class*="tab"]',
        '[role="tab"]',
        'div[class*="view"] button',
        '.tabs button',
        '.nav-tabs a',
        '[class*="switch"]',
        'select'
    ]
    
    found_switchers = []
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
            if elements:
                for el in elements:
                    text = el.text_content() or ""
                    if len(text.strip()) < 50:  # Only small buttons
                        found_switchers.append((selector, text.strip()))
        except:
            pass
    
    if not found_switchers:
        print("    No obvious view switchers found")
        return False
    
    print(f"    Found {len(found_switchers)} potential switchers:")
    for sel, txt in found_switchers[:5]:
        print(f"      - {sel}: '{txt}'")
    
    # Try clicking each one and check if Market Value appears
    for selector, original_text in found_switchers:
        try:
            elements = page.query_selector_all(selector)
            for el in elements:
                el.click()
                page.wait_for_timeout(1000)
                
                content = page.content()
                if 'Market value' in content or 'Market Value' in content:
                    print(f"    ✅ Found Market Value after clicking: {selector}")
                    return True
        except:
            pass
    
    print("    No view switcher found that shows Market Value")
    return False

def extract_market_value(page):
    """Extract Market value from current page view"""
    content = page.content()
    
    # Look for Market value text with value
    patterns = [
        r'Market value:\s*(€[0-9,.]+m?)',
        r'Market value:\s*(€[0-9,.]+)',
        r'Market Value:\s*(€[0-9,.]+m?)',
        r'Market Value:\s*(€[0-9,.]+)',
        r'Value:\s*(€[0-9,.]+m?)',
        r'Value:\s*(€[0-9,.]+)',
        r'€\s*[0-9,]+\.?[0-9]*m?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Clean up value
            value = re.sub(r'\s+', '', value)
            return value
    
    return "–"

def main():
    print("=== Parsing Market Values with Chromium (Interactive) ===\n")
    
    # Load Strasbourg data
    team_files = glob.glob('/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_*.json')
    if not team_files:
        print("❌ No Strasbourg team file found!")
        return
    
    # Use latest file
    team_file = sorted(team_files)[-1]
    print(f"Loading: {team_file}\n")
    
    with open(team_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    players = data.get('players', [])
    print(f"Total players: {len(players)}\n")
    
    parsed_count = 0
    errors = 0
    skipped = 0
    
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
        
        for i, player in enumerate(players):
            player_name = player.get('name', '')
            player_number = player.get('number', '')
            
            # Skip if already has market value
            current_mv = player.get('market_value', '').strip()
            if current_mv and current_mv not in ['–', '-', '']:
                skipped += 1
                print(f"  {i+1}. {player_number}. {player_name} - {current_mv} (SKIPPED)")
                continue
            
            # Build profile URL
            profile_path = player_name.lower().replace(' ', '-')
            player_url = f"https://us.soccerway.com/player/{profile_path}/"
            
            print(f"\n  {i+1}. {player_number}. {player_name}")
            print(f"     Loading: {player_url}")
            
            try:
                # Load page
                page.goto(player_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                
                # Try to switch to view with Market Value
                switched = switch_to_market_value_view(page)
                
                # Extract Market Value
                market_value = extract_market_value(page)
                
                if market_value and market_value != "–":
                    player['market_value'] = market_value
                    parsed_count += 1
                    print(f"     ✅ Market value: {market_value}")
                else:
                    print(f"     ⚠️ Market value: NOT FOUND")
                    errors += 1
                
                # Small delay to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"     ❌ Error: {e}")
                errors += 1
        
        browser.close()
    
    # Save updated data
    data['last_updated'] = '2026-05-13T03:20:00Z'
    
    output_file = team_file.replace('lineup_ai_', 'lineup_ai_mv_final_')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"✅ DONE!")
    print(f"{'='*60}")
    print(f"Parsed: {parsed_count}/{len(players)}")
    print(f"Errors: {errors}")
    print(f"Skipped (already had MV): {skipped}")
    print(f"Saved to: {output_file}")
    
    # Show sample
    print(f"\n📊 Sample (first 5 with market value):")
    for p in data['players'][:5]:
        if p.get('market_value') and p.get('market_value') not in ['–', '-', '']:
            print(f"  {p['number']}. {p['name']} - {p['market_value']}")

if __name__ == "__main__":
    main()
