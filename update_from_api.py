#!/usr/bin/env python3
"""
Update lineup data from API-Football Standings
Uses existing API_TOKEN from FormAlert .env
"""

import os
import json
import glob
from datetime import datetime

# API Configuration
API_TOKEN = "38f9e92432393cf733a92b9dc11afdf3"
API_BASE = "https://v3.football.api-sports.io"

# League IDs from API-Football (2025 season)
LEAGUE_IDS = {
    "England": {"Premier League": 39, "Championship": 40, "League One": 41},
    "France": {"Ligue 1": 61, "Ligue 2": 62},
    "Italy": {"Serie A": 135, "Serie B": 136},
    "Spain": {"LaLiga": 140, "LaLiga 2": 141},
    "Germany": {"Bundesliga": 78, "2. Bundesliga": 79},
    "Netherlands": {"Eredivisie": 88, "Eerste Divisie": 89},
    "Portugal": {"Liga Portugal": 94},
    "Belgium": {"Jupiler Pro League": 144, "Challenger Pro League": 145},
    "Russia": {"Premier League": 235, "First League": 236},
    "Kazakhstan": {"Premier League": 337, "First League": 338},
    "Turkey": {"Süper Lig": 203},
    "Switzerland": {"Super League": 208, "Challenge League": 209},
    "Austria": {"Bundesliga": 218, "2. Liga": 219},
    "Denmark": {"Superliga": 113},
    "Sweden": {"Allsvenskan": 119, "Superettan": 120},
    "Norway": {"Eliteserien": 103},
    "Scotland": {"Premiership": 179},
    "Poland": {"Ekstraklasa": 106},
    "USA": {"MLS": 253},
    "Brazil": {"Serie A": 71, "Serie B": 72},
}


def fetch_standings(league_id: int) -> list:
    """Fetch standings from API-Football"""
    import httpx
    
    url = f"{API_BASE}/standings"
    params = {
        "league": league_id,
        "season": 2025
    }
    headers = {
        "x-apisports-key": API_TOKEN
    }
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("get") == "standings" and data.get("response"):
                    return data["response"][0].get("league", {})
    except Exception as e:
        print(f"Error fetching standings for {league_id}: {e}")
    
    return None


def fetch_team_info(team_id: int) -> dict:
    """Fetch team details from API-Football"""
    import httpx
    
    url = f"{API_BASE}/teams"
    params = {"id": team_id}
    headers = {"x-apisports-key": API_TOKEN}
    
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("get") == "teams" and data.get("response"):
                    return data["response"][0]
    except Exception as e:
        print(f"Error fetching team {team_id}: {e}")
    
    return {}


def build_complete_hierarchy():
    """Build complete team hierarchy from API"""
    hierarchy = {}
    
    for country, leagues in LEAGUE_IDS.items():
        for league_name, league_id in leagues.items():
            print(f"Fetching {country} - {league_name} (ID: {league_id})...")
            
            standings = fetch_standings(league_id)
            if not standings:
                print(f"  ⚠ Could not fetch standings")
                continue
            
            # Get current season teams
            teams_in_league = standings.get("teams", [])
            
            print(f"  ✓ Found {len(teams_in_league)} teams")
            
            if country not in hierarchy:
                hierarchy[country] = {}
            
            teams_data = []
            for team_info in teams_in_league:
                if team_info:
                    team_id = team_info.get("team", {}).get("id")
                    team_name = team_info.get("team", {}).get("name", "Unknown")
                    
                    teams_data.append({
                        "id": str(team_id),
                        "name": team_name
                    })
            
            # Sort by name
            teams_data.sort(key=lambda x: x["name"])
            hierarchy[country][league_name] = teams_data
    
    return hierarchy


def update_json_files(hierarchy: dict):
    """Update/create JSON files for each team"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    # Read existing team files to get full data
    existing_teams = {}
    for f in glob.glob(DATA_DIR + "/lineup_ai_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                team_id = data.get("team", {}).get("id", "")
                if team_id:
                    existing_teams[team_id] = data
        except:
            pass
    
    created_count = 0
    updated_count = 0
    
    for country, leagues in hierarchy.items():
        for league_name, teams in leagues.items():
            for team in teams:
                team_id = team["id"]
                team_name = team["name"]
                
                # Create filename
                league_slug = league_name.lower().replace(" ", "-").replace("/", "-")
                team_slug = team_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
                filename = f"lineup_ai_{league_slug}_team_{team_slug}_{team_id}.json"
                filepath = os.path.join(DATA_DIR, filename)
                
                if team_id in existing_teams:
                    # Update existing file
                    data = existing_teams[team_id]
                    data["last_updated"] = datetime.utcnow().isoformat() + "Z"
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    updated_count += 1
                else:
                    # Create new minimal file
                    data = {
                        "team": {
                            "id": team_id,
                            "name": team_name,
                            "slug": team_slug
                        },
                        "matches": [],  # Empty for now
                        "players": []   # Empty for now - need to fetch separately
                    }
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    created_count += 1
    
    print(f"\n✅ Updated: {updated_count} files")
    print(f"✅ Created: {created_count} files")
    
    return created_count, updated_count


def main():
    print("=== Building Complete Team Hierarchy ===\n")
    
    # Build hierarchy from API
    hierarchy = build_complete_hierarchy()
    
    print(f"\n=== Summary ===")
    print(f"Countries: {len(hierarchy)}")
    total_teams = 0
    for country, leagues in hierarchy.items():
        for league, teams in leagues.items():
            total_teams += len(teams)
    print(f"Total teams: {total_teams}\n")
    
    # Save hierarchy
    output_file = "/home/openclaw/.openclaw/workspace/lineup_hierarchy_api.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(hierarchy, f, indent=2, ensure_ascii=False)
    print(f"Saved hierarchy to: {output_file}")
    
    # Update JSON files
    print("\n=== Updating JSON Files ===")
    created, updated = update_json_files(hierarchy)
    
    print(f"\nDone! Total operations: {created + updated}")


if __name__ == "__main__":
    main()
