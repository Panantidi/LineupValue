#!/usr/bin/env python3
"""Fetch Japan J1 League teams from Soccerway standings."""

import asyncio
import json
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def fetch_japan_j1_teams():
    """Fetch teams from Japan J1 League standings."""
    url = "https://www.soccerway.com/japan/j1-league/standings/6msfOkrp/standings/overall/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            teams = []
            
            # Find standings table
            table = soup.find("table", {"class": "standings"})
            if not table:
                # Try alternative selector
                table = soup.find("table", {"id": re.compile(r"standings")})
            
            if table:
                rows = table.find_all("tr")
                for row in rows:
                    # Find team link
                    link = row.find("a", href=re.compile(r"/teams/"))
                    if link:
                        href = link.get("href", "")
                        # Extract team ID and slug from URL like /teams/japan/tokyo/ABc123/
                        match = re.search(r"/teams/[^/]+/([^/]+)/([A-Za-z0-9]+)/?", href)
                        if match:
                            slug = match.group(1)
                            team_id = match.group(2)
                            name = link.get_text(strip=True)
                            teams.append({
                                "id": team_id,
                                "name": name,
                                "slug": slug
                            })
                            print(f"Found: {name} (ID: {team_id}, slug: {slug})")
            
            if not teams:
                # Try alternative: find all team links in the page
                links = soup.find_all("a", href=re.compile(r"/teams/japan/"))
                seen = set()
                for link in links:
                    href = link.get("href", "")
                    if "/japan/" in href:
                        match = re.search(r"/teams/japan/([^/]+)/([A-Za-z0-9]+)", href)
                        if match:
                            slug = match.group(1)
                            team_id = match.group(2)
                            if team_id not in seen:
                                seen.add(team_id)
                                name = link.get_text(strip=True)
                                if name and len(name) > 2:
                                    teams.append({
                                        "id": team_id,
                                        "name": name,
                                        "slug": slug
                                    })
                                    print(f"Found: {name} (ID: {team_id}, slug: {slug})")
            
            print(f"\nTotal teams found: {len(teams)}")
            return teams
            
        finally:
            await browser.close()

if __name__ == "__main__":
    teams = asyncio.run(fetch_japan_j1_teams())
    
    # Load existing leagues_data.json
    try:
        with open("/home/openclaw/FormAlert/leagues_data.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    
    # Add Japan J1 League
    if "Japan" not in data:
        data["Japan"] = {}
    
    data["Japan"]["J1 League"] = teams
    
    # Save back
    with open("/home/openclaw/FormAlert/leagues_data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(teams)} teams to leagues_data.json")