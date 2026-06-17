#!/usr/bin/env python3
"""
Parse Soccerway Standings via Chromium/Puppeteer
Extracts all teams from league standings tables
"""

import json
import glob
import os
import subprocess
import time
import re
from playwright.sync_api import sync_playwright

# League configuration: (country, championship, soccerway_url)
LEAGUES = [
    # England
    ("England", "Premier League", "https://us.soccerway.com/england/premier-league/"),
    ("England", "Championship", "https://us.soccerway.com/england/championship/"),
    
    # France
    ("France", "Ligue 1", "https://us.soccerway.com/france/ligue-1/"),
    ("France", "Ligue 2", "https://us.soccerway.com/france/ligue-2/"),
    
    # Italy
    ("Italy", "Serie A", "https://us.soccerway.com/italy/serie-a/"),
    ("Italy", "Serie B", "https://us.soccerway.com/italy/serie-b/"),
    
    # Spain
    ("Spain", "LaLiga", "https://us.soccerway.com/spain/laliga/"),
    ("Spain", "LaLiga 2", "https://us.soccerway.com/spain/laliga-2/"),
    
    # Germany
    ("Germany", "Bundesliga", "https://us.soccerway.com/germany/bundesliga/"),
    ("Germany", "2. Bundesliga", "https://us.soccerway.com/germany/bundesliga-2/"),
    
    # Netherlands
    ("Netherlands", "Eredivisie", "https://us.soccerway.com/netherlands/eredivisie/"),
    ("Netherlands", "Eerste Divisie", "https://us.soccerway.com/netherlands/eerste-divisie/"),
    
    # Portugal
    ("Portugal", "Liga Portugal", "https://us.soccerway.com/portugal/liga-portugal/"),
    
    # Belgium
    ("Belgium", "Jupiler Pro League", "https://us.soccerway.com/belgium/jupiler-pro-league/"),
    ("Belgium", "Challenger Pro League", "https://us.soccerway.com/belgium/challenger-pro-league/"),
    
    # Russia
    ("Russia", "Premier League", "https://us.soccerway.com/russia/premier-league/"),
    ("Russia", "First League", "https://us.soccerway.com/russia/first-league/"),
    
    # Kazakhstan
    ("Kazakhstan", "Premier League", "https://us.soccerway.com/kazakhstan/premier-league/"),
    ("Kazakhstan", "First League", "https://us.soccerway.com/kazakhstan/first-league/"),
    
    # Other European leagues
    ("Turkey", "Süper Lig", "https://us.soccerway.com/turkey/super-lig/"),
    ("Switzerland", "Super League", "https://us.soccerway.com/switzerland/super-league/"),
    ("Austria", "Bundesliga", "https://us.soccerway.com/austria/bundesliga/"),
    ("Denmark", "Superliga", "https://us.soccerway.com/denmark/superliga/"),
    ("Sweden", "Allsvenskan", "https://us.soccerway.com/sweden/allsvenskan/"),
    ("Sweden", "Superettan", "https://us.soccerway.com/sweden/superettan/"),
    ("Norway", "Eliteserien", "https://us.soccerway.com/norway/eliteserien/"),
    ("Scotland", "Premiership", "https://us.soccerway.com/scotland/premiership/"),
    ("Poland", "Ekstraklasa", "https://us.soccerway.com/poland/ekstraklasa/"),
    ("Greece", "Super League", "https://us.soccerway.com/greece/super-league/"),
    
    # International
    ("USA", "MLS", "https://us.soccerway.com/usa/mls/"),
    ("Brazil", "Serie A", "https://us.soccerway.com/brazil/serie-a/"),
    ("Argentina", "Liga Profesional", "https://us.soccerway.com/argentina/liga-profesional/"),
    ("Japan", "J1 League", "https://us.soccerway.com/japan/j1-league/"),
]


def get_team_slug(name: str) -> str:
    """Convert team name to URL-friendly slug"""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def parse_standings_from_soccerway(country: str, championship: str, url: str):
    """Parse team list from Soccerway standings page"""
    teams = []
    
    with sync_playwright() as p:
        # Launch Chromium
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Navigate to page
            print(f"Loading {country} - {championship}...")
            response = page.goto(url, wait_until="networkidle", timeout=30000)
            
            if not response or response.status != 200:
                print(f"  Failed to load page: {response.status if response else 'No response'}")
                browser.close()
                return teams
            
            # Wait for standings table
            page.wait_for_selector("table.table-standings", timeout=10000)
            
            # Extract teams from table
            rows = page.query_selector_all("table.table-standings tbody tr")
            
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                
                # Team name is usually in the second cell (index 2 or 3)
                team_cell = cells[2] if len(cells) > 2 else cells[0]
                team_name_elem = team_cell.query_selector("a.team") or team_cell.query_selector("a")
                
                if team_name_elem:
                    team_name = team_name_elem.text_content().strip()
                    team_url = team_name_elem.get_attribute("href")
                    
                    if team_name and team_name != "-":
                        # Extract team ID from URL if possible
                        team_id = ""
                        if team_url:
                            match = re.search(r'/team/(\w+)/', team_url)
                            if match:
                                team_id = match.group(1)
                        
                        teams.append({
                            "name": team_name,
                            "slug": get_team_slug(team_name),
                            "url": team_url,
                            "soccerway_id": team_id
                        })
            
            print(f"  Found {len(teams)} teams")
            
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            browser.close()
    
    return teams


def load_existing_teams():
    """Load existing teams from JSON files"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    existing = {}
    
    for f in glob.glob(DATA_DIR + "/lineup_ai_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
            
            team_id = data.get("team", {}).get("id", "")
            team_name = data.get("team", {}).get("name", "")
            slug = data.get("team", {}).get("slug", "")
            
            if team_id:
                existing[team_id] = {
                    "id": team_id,
                    "name": team_name,
                    "slug": slug,
                    "file": f
                }
        except:
            pass
    
    return existing


def main():
    print("=== Soccerway Standings Parser ===\n")
    
    all_teams = {}
    
    for country, championship, url in LEAGUES:
        print(f"\n[{country}] {championship}")
        teams = parse_standings_from_soccerway(country, championship, url)
        
        if teams:
            if country not in all_teams:
                all_teams[country] = {}
            all_teams[country][championship] = teams
    
    print(f"\n=== Summary ===")
    print(f"Countries: {len(all_teams)}")
    total_teams = 0
    total_leagues = 0
    for country, leagues in all_teams.items():
        total_leagues += len(leagues)
        for league, teams in leagues.items():
            total_teams += len(teams)
            print(f"  {country} - {league}: {len(teams)} teams")
    
    print(f"\nTotal leagues: {total_leagues}")
    print(f"Total teams: {total_teams}")
    
    # Save to file
    output_file = "/home/openclaw/.openclaw/workspace/soccerway_teams.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_teams, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()
