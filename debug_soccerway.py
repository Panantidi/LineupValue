#!/usr/bin/env python3
"""
Debug Soccerway Strasbourg squad page
Find the correct selectors for player rows
"""

from playwright.sync_api import sync_playwright
import json

def debug_page():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        page = browser.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait a bit for JS rendering
        page.wait_for_timeout(5000)
        
        # Get the full HTML
        html = page.content()
        
        # Find all table rows
        print("\n=== Looking for player table ===")
        
        # Try different selectors
        selectors_to_try = [
            "table.table-squad",
            "table.squad-stats",
            "table.table-stats",
            ".lineupTable",
            ".table-squad",
            "[class*='squad']",
            "[class*='table']",
        ]
        
        for selector in selectors_to_try:
            elements = page.query_selector_all(selector)
            print(f"Found {len(elements)} elements with selector: {selector}")
            
            if elements and len(elements) > 0:
                # Print first element structure
                first = elements[0]
                tag = first.evaluate("el => el.tagName")
                classes = first.evaluate("el => el.className")
                print(f"  First element: <{tag}> class=\"{classes}\")")
                
                # Check for rows
                rows = first.query_selector_all("tr")
                print(f"  Found {len(rows)} rows")
                
                if rows:
                    # Print first row structure
                    row = rows[0]
                    cells = row.query_selector_all("td, th")
                    print(f"  First row has {len(cells)} cells")
                    
                    # Print cell contents
                    for i, cell in enumerate(cells[:10]):  # First 10 cells
                        text = cell.text_content().strip()
                        classes = cell.evaluate("el => el.className")
                        print(f"    Cell {i}: \"{text[:50]}...\" class=\"{classes}\"")
        
        # Try to find all player names
        print("\n=== Looking for player names ===")
        
        name_selectors = [
            "[class*='name']",
            "[class*='player']",
            "a[href*='/player/']",
            "[class*='player-name']",
            "td[class*='name']",
            ".lineupTable__cell--name",
        ]
        
        for selector in name_selectors:
            players = page.query_selector_all(selector)
            if players:
                print(f"Found {len(players)} with selector: {selector}")
                for player in players[:5]:
                    name = player.text_content().strip()
                    if name and len(name) < 50:
                        print(f"  - {name}")
        
        # Save full HTML for analysis
        print("\n=== Saving HTML for analysis ===")
        with open('/tmp/strasbourg_debug.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Saved to /tmp/strasbourg_debug.html")
        
        browser.close()

if __name__ == "__main__":
    debug_page()
