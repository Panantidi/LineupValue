"""
LineUp AI Data - Complete version with fixed team lists
Uses hardcoded team lists for top leagues + existing JSON files for others
"""
import json
import glob
import os

HIERARCHY_FILE = "/home/openclaw/FormAlert/leagues_data.json"

def load_complete_hierarchy():
    """Load complete hierarchy with fixed team lists"""
    hierarchy = {}
    
    # Load hardcoded data first
    if os.path.exists(HIERARCHY_FILE):
        with open(HIERARCHY_FILE, 'r', encoding='utf-8') as f:
            hardcoded = json.load(f)
            for country, leagues in hardcoded.items():
                hierarchy[country] = leagues
    
    # Load existing JSON files for other leagues
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    league_mapping = {
        "australia_a-league": ("Australia", "A-League"),
        "austria_2-liga": ("Austria", "2. Liga"),
        "austria_bundesliga": ("Austria", "Bundesliga"),
        "belarus_pershaya-liga": ("Belarus", "First League"),
        "belarus_vysshaya-liga": ("Belarus", "Premier League"),
        "norway_eliteserien": ("Norway", "Eliteserien"),
        "switzerland_super-league": ("Switzerland", "Super League"),
        "finland_veikkausliiga": ("Finland", "Veikkausliiga"),
        "belgium_challenger-pro-league": ("Belgium", "Challenger Pro League"),
        "belgium_jupiler-pro-league": ("Belgium", "Jupiler Pro League"),
        "china_league-one": ("China", "League One"),
        "denmark_superliga": ("Denmark", "Superliga"),
        "england_championship": ("England", "Championship"),
        "england_premier-league": ("England", "Premier League"),
        "france_ligue-1": ("France", "Ligue 1"),
        "france_ligue-2": ("France", "Ligue 2"),
        "germany_bundesliga": ("Germany", "Bundesliga"),
        "germany_bundesliga-2": ("Germany", "2. Bundesliga"),
        "italy_serie-a": ("Italy", "Serie A"),
        "kazakhstan_first-league": ("Kazakhstan", "First League"),
        "kazakhstan_premier-league": ("Kazakhstan", "Premier League"),
        "netherlands_eerste-divisie": ("Netherlands", "Eerste Divisie"),
        "netherlands_eredivisie": ("Netherlands", "Eredivisie"),
        "norway_eliteserien": ("Norway", "Eliteserien"),
        "switzerland_super-league": ("Switzerland", "Super League"),
        "portugal_liga-portugal": ("Portugal", "Liga Portugal"),
        "russia_fnl": ("Russia", "First League"),
        "russia_premier-league": ("Russia", "Premier League"),
        "spain_laliga": ("Spain", "LaLiga"),
        "spain_laliga-2": ("Spain", "LaLiga 2"),
        "sweden_allsvenskan": ("Sweden", "Allsvenskan"),
        "sweden_superettan": ("Sweden", "Superettan"),
        "switzerland_challenge-league": ("Switzerland", "Challenge League"),
        "switzerland_super-league": ("Switzerland", "Super League"),
        "turkey_super-lig": ("Turkey", "Super Lig"),
        "usa_mls": ("USA", "MLS"),
        "world_world-championship": ("World", "World Championship"),
    }
    
    used_team_ids = set()
    
    for f in glob.glob(DATA_DIR + "/lineup_ai_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
            
            filename = os.path.basename(f)
            parts = filename.replace("lineup_ai_", "").replace(".json", "").split("_team_")
            if len(parts) != 2:
                continue
            
            league_slug = parts[0]
            team_id = data.get("team", {}).get("id", "")
            team_name = data.get("team", {}).get("name", "Unknown")
            
            # Skip if already in hardcoded data
            if team_id in used_team_ids:
                continue
            
            # Skip if league is already in hardcoded data
            if league_slug in league_mapping:
                country, championship = league_mapping[league_slug]
                if country in hierarchy and championship in hierarchy[country]:
                    # Check if team already exists
                    if any(t["id"] == team_id for t in hierarchy[country][championship]):
                        continue
            
            if league_slug in league_mapping:
                country, championship = league_mapping[league_slug]
            else:
                continue
            
            if country not in hierarchy:
                hierarchy[country] = {}
            if championship not in hierarchy[country]:
                hierarchy[country][championship] = []
            
            hierarchy[country][championship].append({
                "id": team_id,
                "name": team_name
            })
            used_team_ids.add(team_id)
        
        except Exception as e:
            print(f"Error in {f}: {e}")
    
    # Sort teams alphabetically
    for country in hierarchy:
        for championship in hierarchy[country]:
            hierarchy[country][championship].sort(key=lambda x: x["name"])
    
    return hierarchy

if __name__ == "__main__":
    hierarchy = load_complete_hierarchy()
    print(json.dumps(hierarchy, indent=2, ensure_ascii=False, default=str))
    
    # Print summary
    print(f"\n=== Summary ===")
    print(f"Countries: {len(hierarchy)}")
    total_teams = 0
    total_leagues = 0
    for country, leagues in hierarchy.items():
        total_leagues += len(leagues)
        for league, teams in leagues.items():
            total_teams += len(teams)
            print(f"  {country} - {league}: {len(teams)} teams")
    print(f"Total leagues: {total_leagues}")
    print(f"Total teams: {total_teams}")
