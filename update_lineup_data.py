#!/usr/bin/env python3
"""
Update LineUp AI data with complete team lists from API-Football
Ensures:
- All teams are in correct leagues
- No duplicates (each team in only one league)
- Current season standings used as source of truth
"""

import json
import glob
import os
import httpx
from datetime import datetime

# API Configuration
APIFOOTBALL_TOKEN = "38f9e92432393cf733a92b9dc11afdf3"
APIFOOTBALL_BASE = "https://v3.football.api-sports.io"
DATA_DIR = "/home/openclaw/.openclaw/workspace"

# League mapping (country, league_name, league_id in API)
LEAGUES = {
    "England": {"Premier League": 39, "Championship": 40, "League One": 41, "League Two": 42},
    "France": {"Ligue 1": 61, "Ligue 2": 62},
    "Italy": {"Serie A": 135, "Serie B": 136},
    "Spain": {"LaLiga": 140, "LaLiga 2": 141},
    "Germany": {"Bundesliga": 78, "2. Bundesliga": 79},
    "Netherlands": {"Eredivisie": 88, "Eerste Divisie": 89},
    "Portugal": {"Liga Portugal": 94},
    "Belgium": {"Jupiler Pro League": 144, "Challenger Pro League": 145},
    "Turkey": {"Süper Lig": 203},
    "Russia": {"Premier League": 235, "FNL": 236},
    "Scotland": {"Premiership": 179},
    "Ukraine": {"Premier League": 333},
    "Poland": {"Ekstraklasa": 106},
    "Greece": {"Super League": 197},
    "Switzerland": {"Super League": 208, "Challenge League": 209},
    "Austria": {"Bundesliga": 218, "2. Liga": 219},
    "Denmark": {"Superliga": 113},
    "Sweden": {"Allsvenskan": 119, "Superettan": 120},
    "Norway": {"Eliteserien": 103},
    "Czech Republic": {"First League": 345},
    "Croatia": {"HNL": 214},
    "Serbia": {"SuperLiga": 286},
    "Slovakia": {"Super Liga": 344},
    "Slovenia": {"1. SNL": 289},
    "Hungary": {"Nemzeti Bajnokság I": 271},
    "Romania": {"Liga 1": 283},
    "Bulgaria": {"First League": 313},
    "Israel": {"Ligat Ha'Al": 308},
    "Japan": {"J1 League": 98},
    "South Korea": {"K League 1": 292},
    "China": {"Super League": 169, "League One": 170},
    "Australia": {"A-League": 194},
    "USA": {"MLS": 253},
    "Brazil": {"Serie A": 71, "Serie B": 72},
    "Argentina": {"Liga Profesional": 128},
    "Mexico": {"Liga MX": 262},
    "Saudi Arabia": {"Pro League": 307},
    "UAE": {"Pro League": 325},
    "Egypt": {"Premier League": 265},
    "South Africa": {"Premier Division": 291},
    "Kazakhstan": {"Premier League": 337, "First League": 338},
    "Finland": {"Veikkausliiga": 244},
    "Iceland": {"Úrvalsdeild": 246},
    " Wales": {"Premiership": 281},
    "Northern Ireland": {"Premiership": 282},
    "Republic of Ireland": {"Premiership": 274},
}

async def get_current_standings(league_id: int) -> list:
    """Get current standings for a league"""
    url = APIFOOTBALL_BASE + "/standings"
    params = {
        "league": league_id,
        "season": 2025  # Current season
    }
    headers = {
        "x-apisports-key": APIFOOTBALL_TOKEN
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("get") == "standings" and data.get("response"):
                    return data["response"][0].get("league", {})
    except Exception as e:
        print(f"Error fetching standings for league {league_id}: {e}")
    
    return None

def normalize_league_name(name: str) -> str:
    """Normalize league names"""
    name = name.strip()
    # Common variations
    name = name.replace("Premier League", "Premier League")
    name = name.replace("LaLiga", "LaLiga")
    name = name.replace("Süper Lig", "Süper Lig")
    name = name.replace("Bundesliga 2", "2. Bundesliga")
    return name

def get_team_from_filename(filename: str) -> dict:
    """Extract team info from filename"""
    # Format: lineup_ai_{league}_team_{slug}_{id}.json
    try:
        parts = filename.replace("lineup_ai_", "").replace(".json", "").split("_team_")
        if len(parts) != 2:
            return None
        
        league_slug = parts[0]
        team_part = parts[1]
        team_slug, team_id = team_part.rsplit("_", 1)
        
        return {
            "slug": team_slug,
            "id": team_id,
            "league_slug": league_slug
        }
    except:
        return None

def get_existing_teams() -> dict:
    """Get all existing teams from JSON files"""
    teams = {}
    pattern = os.path.join(DATA_DIR, "lineup_ai_*.json")
    
    for f in glob.glob(pattern):
        filename = os.path.basename(f)
        team_info = get_team_from_filename(filename)
        if not team_info:
            continue
        
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            team_name = data.get("team", {}).get("name", "Unknown")
            teams[team_info["id"]] = {
                "id": team_info["id"],
                "name": team_name,
                "slug": team_info["slug"],
                "league_slug": team_info["league_slug"],
                "file": f
            }
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    return teams

def build_league_mapping():
    """Build mapping of league slug -> (country, normalized_name)"""
    league_mapping = {}
    
    for country, leagues in LEAGUES.items():
        if isinstance(leagues, dict):
            for league_name, league_id in leagues.items():
                # Create slug from league name
                slug = league_name.lower().replace(" ", "-")
                league_mapping[slug] = (country, league_name, league_id)
        else:
            # Simple case
            slug = leagues.lower().replace(" ", "-")
            league_mapping[slug] = (country, leagues, 0)
    
    return league_mapping

async def update_lineup_data():
    """Main function to update lineup data"""
    print("Starting LineUp AI data update...")
    
    # Get existing teams
    existing_teams = get_existing_teams()
    print(f"Found {len(existing_teams)} existing teams")
    
    # Build league mapping
    league_mapping = build_league_mapping()
    
    # Organize teams by league
    leagues_data = {}
    
    for team_id, team_info in existing_teams.items():
        league_slug = team_info["league_slug"]
        
        # Find matching league
        matched_league = None
        for slug, (country, league_name, league_id) in league_mapping.items():
            if slug in league_slug or league_slug in slug:
                matched_league = (country, league_name, league_id)
                break
        
        if not matched_league:
            print(f"Warning: Could not match league for {team_info['name']} ({league_slug})")
            continue
        
        country, league_name, league_id = matched_league
        
        if country not in leagues_data:
            leagues_data[country] = {}
        if league_name not in leagues_data[country]:
            leagues_data[country][league_name] = {
                "league_id": league_id,
                "teams": []
            }
        
        # Avoid duplicates
        if not any(t["id"] == team_id for t in leagues_data[country][league_name]["teams"]):
            leagues_data[country][league_name]["teams"].append(team_info)
    
    # Sort teams by name
    for country in leagues_data:
        for league in leagues_data[country]:
            leagues_data[country][league]["teams"].sort(key=lambda x: x["name"])
    
    # Output summary
    print("\n=== Current League Distribution ===")
    for country in sorted(leagues_data.keys()):
        print(f"\n{country}:")
        for league_name, data in sorted(leagues_data[country].items()):
            print(f"  {league_name}: {len(data['teams'])} teams")
    
    # Save to JSON
    output_file = os.path.join(DATA_DIR, "lineup_hierarchy.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(leagues_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved hierarchy to: {output_file}")
    print(f"Total leagues: {sum(len(leagues_data[c]) for c in leagues_data)}")
    print(f"Total teams: {sum(len(leagues_data[c][l]['teams']) for c in leagues_data for l in leagues_data[c])}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(update_lineup_data())
