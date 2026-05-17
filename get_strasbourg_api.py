#!/usr/bin/env python3
"""
Get Strasbourg squad stats from API-Football
Uses: https://v3.football.api-sports.io
Token: 38f9e92432393cf733a92b9dc11afdf3
"""

import json
import httpx
from datetime import datetime

# API Configuration
API_TOKEN = "38f9e92432393cf733a92b9dc11afdf3"
API_BASE = "https://v3.football.api-sports.io"

# Strasbourg team ID from API-Football
STRASBOURG_TEAM_ID = "95"  # API-Football ID for Strasbourg


def fetch_squad(team_id: int, season: int = 2024) -> dict:
    """Fetch squad from API-Football"""
    
    url = f"{API_BASE}/players"
    params = {
        "team": team_id,
        "season": 2024  # Use 2024 for free API plan
    }
    headers = {
        "x-apisports-key": API_TOKEN
    }
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url, params=params, headers=headers)
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"API response: get={data.get('get')}, results={data.get('results')}")
                
                if data.get("get") == "players" and data.get("response"):
                    return {
                        "success": True,
                        "players": data["response"],
                        "total": data.get("paging", {}).get("total", 0)
                    }
                else:
                    print(f"Unexpected API response format")
                    print(f"Response: {data}")
            else:
                print(f"Error: Status {response.status_code}")
                print(f"Response: {response.text[:500]}")
                
    except Exception as ex:
        print(f"Exception: {ex}")
        import traceback
        traceback.print_exc()
    
    return {"success": False, "players": [], "error": str(ex) if 'ex' in locals() else "Unknown error"}


def fetch_player_stats(player_id: int, season: int = 2024) -> dict:
    """Fetch specific player stats"""
    
    url = f"{API_BASE}/players"
    params = {
        "id": player_id,
        "season": season
    }
    headers = {"x-apisports-key": API_TOKEN}
    
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("get") == "players" and data.get("response"):
                    return data["response"][0]
    except Exception as e:
        print(f"Error for player {player_id}: {e}")
    
    return {}


def extract_stats_from_api(player_data: dict) -> dict:
    """Extract stats from API-Football response"""
    
    stats = {
        "apps": "0",
        "min": "0",
        "goal": "0",
        "assist": "0",
        "yellow_card": "0",
        "red_card": "0"
    }
    
    if isinstance(player_data, dict):
        if "statistics" in player_data and isinstance(player_data["statistics"], list):
            for stat in player_data["statistics"]:
                if not isinstance(stat, dict):
                    continue
                
                games = stat.get("games", {})
                goals = stat.get("goals", {})
                cards = stat.get("cards", {})
                
                apps = games.get("appearences", 0) if games else 0
                mins = stat.get("minutes", 0) if stat else 0
                goals_total = goals.get("total", 0) if goals else 0
                assists = goals.get("assists", 0) if goals else 0
                yellow = cards.get("yellow", 0) if cards else 0
                red = cards.get("red", 0) if cards else 0
                
                # Handle None values
                apps = apps if apps else 0
                mins = mins if mins else 0
                goals_total = goals_total if goals_total else 0
                assists = assists if assists else 0
                yellow = yellow if yellow else 0
                red = red if red else 0
                
                stats["apps"] = str(int(stats["apps"]) + apps)
                stats["min"] = str(int(stats["min"]) + mins)
                stats["goal"] = str(int(stats["goal"]) + goals_total)
                stats["assist"] = str(int(stats["assist"]) + assists)
                stats["yellow_card"] = str(int(stats["yellow_card"]) + yellow)
                stats["red_card"] = str(int(stats["red_card"]) + red)
    
    return stats


def main():
    print(f"=== Fetching Strasbourg Squad from API-Football ===\n")
    
    print(f"Fetching squad for team ID {STRASBOURG_TEAM_ID}...")
    
    result = fetch_squad(STRASBOURG_TEAM_ID)
    
    if not result.get("success"):
        print("❌ Failed to fetch squad")
        if "error" in result:
            print(f"Error: {result['error']}")
        return
    
    players = result["players"]
    total = result["total"]
    
    print(f"✅ Found {len(players)} players (API shows {total} total)\n")
    
    # Extract data
    lineup_players = []
    
    for player in players:
        player_info = player.get("player", {})
        stats = extract_stats_from_api(player)
        
        # Basic info
        name = player_info.get("name", "Unknown")
        number = player_info.get("number", "-")
        position = player_info.get("position", "-")
        age = player_info.get("age", "-")
        nationality = player_info.get("nationality", "-")
        
        # Map position to our format
        pos_code = "-"
        if position == "Goalkeeper":
            pos_code = "GK"
        elif position in ["Defender", "Centre-Back", "Right-Back", "Left-Back"]:
            pos_code = "DEF"
        elif position in ["Midfielder", "Defensive Midfielder", "Central Midfielder", "Winger"]:
            pos_code = "MID"
        elif position in ["Attacker", "Forward", "Centre-Forward", "Right Winger", "Left Winger"]:
            pos_code = "FWD"
        
        lineup_player = {
            "number": str(number) if number else "-",
            "name": name,
            "national": nationality,
            "position": pos_code,
            "age": str(age) if age and str(age).isdigit() else "-",
            "apps": stats["apps"],
            "min": stats["min"],
            "goal": stats["goal"],
            "assist": stats["assist"],
            "yellow_card": stats["yellow_card"],
            "red_card": stats["red_card"],
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
        
        lineup_players.append(lineup_player)
        
        # Show progress
        if int(stats["apps"]) > 0:
            print(f"  ✅ {number}. {name} | {nationality} | {pos_code} | Apps: {stats['apps']}, G: {stats['goal']}, A: {stats['assist']}")
        else:
            print(f"  ⚪ {number}. {name} | {nationality} | {pos_code}")
    
    # Create final JSON
    team_data = {
        "team": {
            "id": "nP6UzIU1",
            "name": "Strasbourg",
            "slug": "strasbourg",
            "league": "Ligue 1",
            "country": "France"
        },
        "matches": [],
        "players": lineup_players
    }
    
    # Save
    output_file = "/home/openclaw/.openclaw/workspace/lineup_ai_france_ligue-1_team_strasbourg_nP6UzIU1_api.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(team_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    with_stats = sum(1 for p in lineup_players if p['apps'] != "0")
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"Team: Strasbourg")
    print(f"Players: {len(lineup_players)}")
    print(f"With stats: {with_stats}/{len(lineup_players)}")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
