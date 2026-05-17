"""
LineUp AI Data - Final version with proper hierarchy
Uses lineup_hierarchy.json as source of truth
"""
import json
import os
import glob

HIERARCHY_FILE = "/home/openclaw/.openclaw/workspace/lineup_hierarchy.json"

def build_clean_hierarchy():
    """Build clean hierarchy from JSON files - ensures each team is in only ONE league"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    
    # League mapping
    league_to_country_champ = {
        "australia_a-league": ("Australia", "A-League"),
        "austria_2-liga": ("Austria", "2. Liga"),
        "austria_bundesliga": ("Austria", "Bundesliga"),
        "belarus_pershaya-liga": ("Belarus", "First League"),
        "belarus_vysshaya-liga": ("Belarus", "Premier League"),
        "belgium_challenger-pro-league": ("Belgium", "Challenger Pro League"),
        "belgium_jupiler-pro-league": ("Belgium", "Jupiler Pro League"),
        "china_league-one": ("China", "League One"),
        "china_super-league": ("China", "Super League"),
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
        "portugal_liga-portugal": ("Portugal", "Liga Portugal"),
        "russia_fnl": ("Russia", "First League"),
        "russia_premier-league": ("Russia", "Premier League"),
        "spain_laliga": ("Spain", "LaLiga"),
        "spain_laliga-2": ("Spain", "LaLiga 2"),
        "sweden_allsvenskan": ("Sweden", "Allsvenskan"),
        "sweden_superettan": ("Sweden", "Superettan"),
        "switzerland_challenge-league": ("Switzerland", "Challenge League"),
        "switzerland_super-league": ("Switzerland", "Super League"),
        "turkey_super-lig": ("Turkey", "Süper Lig"),
        "usa_mls": ("USA", "MLS"),
        "ligue-1": ("France", "Ligue 1"),
        "ligue-2": ("France", "Ligue 2"),
    }
    
    hierarchy = {}
    used_team_ids = {}  # Track which teams are already assigned
    
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
            
            # Skip if team already assigned to another league
            if team_id in used_team_ids:
                existing = used_team_ids[team_id]
                print(f"Duplicate team {team_name} (ID: {team_id}): already in {existing}, skipping {league_slug}")
                continue
            
            # Get country and championship
            if league_slug in league_to_country_champ:
                country, championship = league_to_country_champ[league_slug]
            else:
                print(f"Warning: Unknown league slug: {league_slug}")
                continue
            
            if country not in hierarchy:
                hierarchy[country] = {}
            if championship not in hierarchy[country]:
                hierarchy[country][championship] = []
            
            hierarchy[country][championship].append({
                "id": team_id,
                "name": team_name
            })
            used_team_ids[team_id] = f"{country} - {championship}"
        
        except Exception as e:
            print(f"Error in {f}: {e}")
    
    # Sort teams alphabetically
    for country in hierarchy:
        for championship in hierarchy[country]:
            hierarchy[country][championship].sort(key=lambda x: x["name"])
    
    return hierarchy

def load_lineup_hierarchy():
    """Load hierarchy (always rebuild to ensure freshness)"""
    return build_clean_hierarchy()

if __name__ == "__main__":
    hierarchy = load_lineup_hierarchy()
    print(json.dumps(hierarchy, indent=2, ensure_ascii=False))
    
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
