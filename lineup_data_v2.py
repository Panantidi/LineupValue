"""
LineUp AI Data - Load from pre-built hierarchy
This is the SOURCE OF TRUTH for team/championship/country relationships
"""
import json
import os

HIERARCHY_FILE = "/home/openclaw/.openclaw/workspace/lineup_hierarchy.json"

def load_lineup_hierarchy():
    """Load pre-built hierarchy from JSON file"""
    if not os.path.exists(HIERARCHY_FILE):
        print(f"Warning: {HIERARCHY_FILE} not found. Building from files...")
        return build_from_files()
    
    try:
        with open(HIERARCHY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading hierarchy: {e}")
        return build_from_files()

def build_from_files():
    """Fallback: build from individual JSON files"""
    import glob
    
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    teams = {}
    
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
            
            # Simple country detection
            country = "Unknown"
            championship = league_slug.replace("-", " ").title()
            
            if "france" in league_slug.lower():
                country = "France"
                if "ligue-1" in league_slug.lower():
                    championship = "Ligue 1"
                elif "ligue-2" in league_slug.lower():
                    championship = "Ligue 2"
            elif "england" in league_slug.lower():
                country = "England"
                if "premier-league" in league_slug.lower():
                    championship = "Premier League"
                elif "championship" in league_slug.lower():
                    championship = "Championship"
            elif "italy" in league_slug.lower():
                country = "Italy"
                championship = "Serie A"
            elif "spain" in league_slug.lower():
                country = "Spain"
                championship = "LaLiga"
            elif "germany" in league_slug.lower():
                country = "Germany"
                championship = "Bundesliga"
            elif "netherlands" in league_slug.lower():
                country = "Netherlands"
                championship = "Eredivisie"
            elif "portugal" in league_slug.lower():
                country = "Portugal"
                championship = "Liga Portugal"
            elif "belgium" in league_slug.lower():
                country = "Belgium"
                if "jupiler" in league_slug.lower():
                    championship = "Jupiler Pro League"
                else:
                    championship = "Challenger Pro League"
            elif "russia" in league_slug.lower():
                country = "Russia"
                championship = "Premier League"
            elif "kazakhstan" in league_slug.lower():
                country = "Kazakhstan"
                if "premier-league" in league_slug.lower():
                    championship = "Premier League"
                else:
                    championship = "First League"
            
            if country not in teams:
                teams[country] = {}
            if championship not in teams[country]:
                teams[country][championship] = []
            
            if not any(t["id"] == team_id for t in teams[country][championship]):
                teams[country][championship].append({
                    "id": team_id,
                    "name": team_name,
                    "file": f
                })
        
        except Exception as e:
            print(f"Error in {f}: {e}")
    
    # Sort teams
    for country in teams:
        for championship in teams[country]:
            teams[country][championship].sort(key=lambda x: x["name"])
    
    return teams

if __name__ == "__main__":
    hierarchy = load_lineup_hierarchy()
    print(json.dumps(hierarchy, indent=2, ensure_ascii=False, default=str))
