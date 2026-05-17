#!/usr/bin/env python3
"""
Extract player data from specific Soccerway section
Uses your XPath: //*[@id="overall-all-table"]/div[1]/div[5]/div[1]
"""

from playwright.sync_api import sync_playwright
import json
import re

def extract_from_section(url):
    """Extract player data from the specified section"""
    
    players = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        page = browser.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for JS rendering
        print("Waiting for page to render...")
        page.wait_for_timeout(10000)
        
        # Try to find the section by XPath
        # Note: Playwright uses CSS selectors, not XPath directly
        # We'll use JavaScript to execute XPath
        
        xpath = '//*[@id="overall-all-table"]/div[1]/div[5]/div[1]'
        
        # Execute JavaScript to find element by XPath
        section = page.evaluate(f"""() => {{
            const xpath = '{xpath}';
            const result = document.evaluate(
                xpath,
                document,
                null,
                XPathResult.FIRST_ORDERED_NODE_TYPE,
                null
            );
            return result.singleNodeValue;
        }}""")
        
        if section:
            print("✅ Found the section!")
            
            # Get inner HTML
            html = page.evaluate(f"""() => {{
                const xpath = '{xpath}';
                const result = document.evaluate(
                    xpath,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                const elem = result.singleNodeValue;
                return elem ? elem.innerHTML : '';
            }}""")
            
            print(f"Section HTML: {len(html)} chars")
            
            # Parse the HTML for player data
            # Look for table rows
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
            
            print(f"Found {len(rows)} rows")
            
            for i, row in enumerate(rows):
                # Skip if it's a header row
                if '<th' in row or 'Name' in row or 'Number' in row:
                    print(f"  Skipping header row {i}")
                    continue
                
                # Extract cells
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                
                if len(cells) < 8:
                    continue
                
                try:
                    # Extract data based on your table structure
                    # Assuming: Number, Name, Age, Apps, Min, Goals, Assists, Yellow, Red
                    
                    # Number (jersey)
                    number = re.sub(r'<[^>]+>', '', cells[0]).strip() if len(cells) > 0 else "-"
                    
                    # Name (with link)
                    name_match = re.search(r'<a[^>]+href="[^"]*player[^"]*"[^>]*>([^<]+)</a>', cells[1]) if len(cells) > 1 else None
                    name = name_match.group(1).strip() if name_match else re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else "-"
                    
                    if not name:
                        continue
                    
                    # Age
                    age = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else "-"
                    
                    # Apps
                    apps = re.sub(r'<[^>]+>', '', cells[3]).strip() if len(cells) > 3 else "-"
                    
                    # Minutes
                    minutes = re.sub(r'<[^>]+>', '', cells[4]).strip() if len(cells) > 4 else "-"
                    
                    # Goals
                    goals = re.sub(r'<[^>]+>', '', cells[5]).strip() if len(cells) > 5 else "-"
                    
                    # Assists
                    assists = re.sub(r'<[^>]+>', '', cells[6]).strip() if len(cells) > 6 else "-"
                    
                    # Yellow cards
                    yellow = re.sub(r'<[^>]+>', '', cells[7]).strip() if len(cells) > 7 else "-"
                    
                    # Red cards
                    red = re.sub(r'<[^>]+>', '', cells[8]).strip() if len(cells) > 8 else "-"
                    
                    player = {
                        "number": number if number and number.isdigit() else "-",
                        "name": name,
                        "national": "-",  # Will need separate extraction
                        "position": "-",  # Will need separate extraction
                        "age": age if age and age.isdigit() else "-",
                        "apps": apps if apps and apps.isdigit() else "-",
                        "min": minutes if minutes and minutes.isdigit() else "-",
                        "goal": goals if goals and goals.isdigit() else "-",
                        "assist": assists if assists and assists.isdigit() else "-",
                        "yellow_card": yellow if yellow and yellow.isdigit() else "-",
                        "red_card": red if red and red.isdigit() else "-",
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
                    print(f"  ✅ {number}. {name} | Age: {age} | Apps: {apps} | G: {goals} | A: {assists}")
                    
                except Exception as e:
                    print(f"  ⚠️ Error parsing row {i}: {e}")
                    continue
        else:
            print("❌ Section not found!")
            print("Trying alternative selectors...")
            
            # Try to find the lineup table
            lineup = page.query_selector("div.lineupTable")
            if lineup:
                print("✅ Found lineupTable div")
                # Get all rows
                rows = lineup.query_selector_all(".lineupTable__row")
                print(f"Found {len(rows)} player rows")
                
                for row in rows:
                    cells = row.query_selector_all(".lineupTable__cell")
                    if len(cells) < 8:
                        continue
                    
                    try:
                        number = cells[0].text_content().strip() if cells[0] else "-"
                        
                        name_link = row.query_selector(".lineupTable__cell--name a")
                        name = name_link.text_content().strip() if name_link else cells[1].text_content().strip() if len(cells) > 1 else "-"
                        
                        if not name or name in ['Name', 'Position']:
                            continue
                        
                        age = cells[2].text_content().strip() if len(cells) > 2 and cells[2] else "-"
                        apps = cells[3].text_content().strip() if len(cells) > 3 and cells[3] else "-"
                        minutes = cells[4].text_content().strip() if len(cells) > 4 and cells[4] else "-"
                        goals = cells[5].text_content().strip() if len(cells) > 5 and cells[5] else "-"
                        assists = cells[6].text_content().strip() if len(cells) > 6 and cells[6] else "-"
                        yellow = cells[7].text_content().strip() if len(cells) > 7 and cells[7] else "-"
                        red = cells[8].text_content().strip() if len(cells) > 8 and cells[8] else "-"
                        
                        player = {
                            "number": number,
                            "name": name,
                            "national": "-",
                            "position": "-",
                            "age": age,
                            "apps": apps,
                            "min": minutes,
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
                        
                        players.append(player)
                        print(f"  ✅ {number}. {name} | Age: {age} | Apps: {apps}")
                        
                    except Exception as e:
                        print(f"  ⚠️ Error: {e}")
                        continue
        
        browser.close()
    
    return players


def main():
    url = "https://us.soccerway.com/team/strasbourg/nP6UzIU1/squad/"
    
    print(f"=== Extracting from {url} ===\n")
    
    players = extract_from_section(url)
    
    if players:
        print(f"\n✅ Extracted {len(players)} players")
        
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
            "players": players
        }
        
        output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(team_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved to: {output_file}")
        
        # Show summary
        print(f"\nSample players:")
        for p in players[:5]:
            print(f"  {p['number']}. {p['name']} | {p['age']} | {p['apps']} apps | {p['goal']} goals")
    else:
        print("❌ No data extracted")


if __name__ == "__main__":
    main()
