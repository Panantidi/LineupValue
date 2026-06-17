#!/usr/bin/env python3
"""Parse Japan J1 League teams from Soccerway standings."""

import json
import re
from playwright.sync_api import sync_playwright

def get_team_slug(name: str) -> str:
    """Convert team name to URL-friendly slug"""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def parse_japan_j1():
    """Parse Japan J1 League teams from Soccerway standings"""
    url = "https://us.soccerway.com/japan/j1-league/"
    teams = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading Japan J1 League...")
            response = page.goto(url, wait_until="networkidle", timeout=60000)
            
            if not response or response.status != 200:
                print(f"Failed: {response.status if response else 'No response'}")
                browser.close()
                return teams
            
            # Wait for standings table
            page.wait_for_selector("table", timeout=10000)
            
            # Extract teams from table
            rows = page.query_selector_all("table tbody tr")
            print(f"Found {len(rows)} rows")
            
            for row in rows:
                # Find team link
                link = row.query_selector("a[href*='/teams/']")
                if link:
                    team_name = link.text_content().strip()
                    team_url = link.get_attribute("href")
                    
                    if team_name and team_name != "-":
                        # Extract team ID from URL
                        team_id = ""
                        if team_url:
                            match = re.search(r'/teams/[^/]+/([A-Za-z0-9]+)', team_url)
                            if match:
                                team_id = match.group(1)
                        
                        teams.append({
                            "id": team_id,
                            "name": team_name,
                            "slug": get_team_slug(team_name)
                        })
                        print(f"  {team_name} (ID: {team_id})")
            
            print(f"\nTotal: {len(teams)} teams")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
    
    return teams


if __name__ == "__main__":
    teams = parse_japan_j1()
    
    if teams:
        # Load existing leagues_data.json
        leagues_file = "/home/openclaw/FormAlert/leagues_data.json"
        with open(leagues_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Update Japan J1 League
        if "Japan" not in data:
            data["Japan"] = {}
        data["Japan"]["J1 League"] = teams
        
        # Save
        with open(leagues_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved {len(teams)} teams to leagues_data.json")