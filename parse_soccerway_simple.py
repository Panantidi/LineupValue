#!/usr/bin/env python3
"""
Simplified Soccerway parser - only top leagues first
"""

import json
import os
from playwright.sync_api import sync_playwright
import re

# Focus on main leagues first
LEAGUES = [
    ("England", "Premier League", "https://us.soccerway.com/england/premier-league/"),
    ("France", "Ligue 1", "https://us.soccerway.com/france/ligue-1/"),
    ("Italy", "Serie A", "https://us.soccerway.com/italy/serie-a/"),
    ("Spain", "LaLiga", "https://us.soccerway.com/spain/laliga/"),
    ("Germany", "Bundesliga", "https://us.soccerway.com/germany/bundesliga/"),
    ("Netherlands", "Eredivisie", "https://us.soccerway.com/netherlands/eredivisie/"),
    ("Portugal", "Liga Portugal", "https://us.soccerway.com/portugal/liga-portugal/"),
    ("Russia", "Premier League", "https://us.soccerway.com/russia/premier-league/"),
    ("Kazakhstan", "Premier League", "https://us.soccerway.com/kazakhstan/premier-league/"),
]


def get_team_slug(name: str) -> str:
    slug = name.lower().replace(' ', '-').replace("'", '').replace('.', '')
    return re.sub(r'[-]+', '-', slug).strip('-')


def parse_league(country, championship, url):
    """Parse a single league"""
    teams = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            page = browser.new_page()
            
            page.goto(url, wait_until='networkidle', timeout=30000)
            page.wait_for_selector('table.table-standings', timeout=10000)
            
            rows = page.query_selector_all('table.table-standings tbody tr')
            
            for row in rows:
                cells = row.query_selector_all('td')
                if len(cells) < 3:
                    continue
                
                team_cell = cells[2]
                team_link = team_cell.query_selector('a.team') or team_cell.query_selector('a')
                
                if team_link:
                    name = team_link.text_content().strip()
                    href = team_link.get_attribute('href')
                    
                    if name and name != '-':
                        teams.append({
                            'name': name,
                            'slug': get_team_slug(name),
                            'href': href
                        })
            
            browser.close()
            print(f"✓ {country} - {championship}: {len(teams)} teams")
            
    except Exception as e:
        print(f"✗ {country} - {championship}: Error - {e}")
    
    return teams


def main():
    print("=== Parsing Soccerway Standings ===\n")
    
    all_data = {}
    
    for country, championship, url in LEAGUES:
        teams = parse_league(country, championship, url)
        if teams:
            if country not in all_data:
                all_data[country] = {}
            all_data[country][championship] = teams
    
    # Save
    output = '/home/openclaw/.openclaw/workspace/soccerway_standings.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {output}")
    
    # Summary
    total = sum(len(t) for l in all_data.values() for t in l.values())
    print(f"Total: {len(all_data)} countries, {total} teams")


if __name__ == "__main__":
    main()
