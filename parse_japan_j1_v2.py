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
    url = "https://us.soccerway.com/japan/j1-league/standings/"
    teams = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading Japan J1 League standings...")
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            if not response or response.status != 200:
                print(f"Failed: {response.status if response else 'No response'}")
                browser.close()
                return teams
            
            # Wait for page to render
            page.wait_for_timeout(5000)
            
            # Try to find standings table
            html = page.content()
            
            # Find team links in the page
            links = page.query_selector_all("a[href*='/teams/japan/']")
            print(f"Found {len(links)} Japan team links")
            
            seen = set()
            for link in links:
                team_name = link.text_content().strip()
                team_url = link.get_attribute("href")
                
                if team_name and len(team_name) > 2 and team_url:
                    # Extract team ID from URL
                    match = re.search(r'/teams/japan/([^/]+)/([A-Za-z0-9]+)', team_url)
                    if match:
                        slug = match.group(1)
                        team_id = match.group(2)
                        
                        if team_id not in seen:
                            seen.add(team_id)
                            teams.append({
                                "id": team_id,
                                "name": team_name,
                                "slug": slug
                            })
                            print(f"  {team_name} (ID: {team_id}, slug: {slug})")
            
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
        
        print(f"\n✅ Saved {len(teams)} teams to leagues_data.json")
    else:
        print("\n❌ No teams found")