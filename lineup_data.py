"""
LineUp AI Data - Country/Championship/Team hierarchy
"""
import json
import glob
import os

def build_lineup_hierarchy():
    """Build country -> championship -> teams hierarchy from JSON files"""
    DATA_DIR = "/home/openclaw/.openclaw/workspace"
    pattern = DATA_DIR + "/lineup_ai_*.json"
    
    hierarchy = {}  # {country: {championship: [teams]}}
    
    for f in glob.glob(pattern):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            # Parse filename to get league info
            filename = os.path.basename(f)
            # Format: lineup_ai_{league}_team_{team_slug}_{id}.json
            parts = filename.replace("lineup_ai_", "").replace(".json", "").split("_team_")
            if len(parts) != 2:
                continue
                
            league_slug = parts[0]
            team_slug = parts[1]
            
            # Map league slug to readable names
            league_parts = league_slug.split("_")
            
            # Determine country and championship
            country = "Unknown"
            championship = league_slug.replace("-", " ").title()
            
            # Simple country detection based on league name
            if "australia" in league_slug.lower():
                country = "Australia"
            elif "austria" in league_slug.lower():
                country = "Austria"
            elif "belarus" in league_slug.lower():
                country = "Belarus"
            elif "belgium" in league_slug.lower():
                country = "Belgium"
            elif "china" in league_slug.lower():
                country = "China"
            elif "denmark" in league_slug.lower():
                country = "Denmark"
            elif "england" in league_slug.lower():
                country = "England"
            elif "france" in league_slug.lower():
                country = "France"
            elif "germany" in league_slug.lower():
                country = "Germany"
            elif "italy" in league_slug.lower():
                country = "Italy"
            elif "kazakhstan" in league_slug.lower():
                country = "Kazakhstan"
            elif "netherlands" in league_slug.lower():
                country = "Netherlands"
            elif "norway" in league_slug.lower():
                country = "Norway"
            elif "portugal" in league_slug.lower():
                country = "Portugal"
            elif "russia" in league_slug.lower():
                country = "Russia"
            elif "spain" in league_slug.lower():
                country = "Spain"
            elif "sweden" in league_slug.lower():
                country = "Sweden"
            elif "switzerland" in league_slug.lower():
                country = "Switzerland"
            elif "turkey" in league_slug.lower():
                country = "Turkey"
            elif "usa" in league_slug.lower():
                country = "USA"
            elif "scotland" in league_slug.lower():
                country = "Scotland"
            elif "ukraine" in league_slug.lower():
                country = "Ukraine"
            elif "poland" in league_slug.lower():
                country = "Poland"
            elif "greece" in league_slug.lower():
                country = "Greece"
            elif "czech" in league_slug.lower():
                country = "Czech Republic"
            elif "serbia" in league_slug.lower():
                country = "Serbia"
            elif "croatia" in league_slug.lower():
                country = "Croatia"
            elif "slovakia" in league_slug.lower():
                country = "Slovakia"
            elif "slovenia" in league_slug.lower():
                country = "Slovenia"
            elif "hungary" in league_slug.lower():
                country = "Hungary"
            elif "romania" in league_slug.lower():
                country = "Romania"
            elif "bulgaria" in league_slug.lower():
                country = "Bulgaria"
            elif "serbia" in league_slug.lower():
                country = "Serbia"
            elif "bosnia" in league_slug.lower():
                country = "Bosnia and Herzegovina"
            elif "montenegro" in league_slug.lower():
                country = "Montenegro"
            elif "macedonia" in league_slug.lower():
                country = "North Macedonia"
            elif "albania" in league_slug.lower():
                country = "Albania"
            elif "kosovo" in league_slug.lower():
                country = "Kosovo"
            elif "israel" in league_slug.lower():
                country = "Israel"
            elif "japan" in league_slug.lower():
                country = "Japan"
            elif "south_korea" in league_slug.lower():
                country = "South Korea"
            elif "china" in league_slug.lower():
                country = "China"
            elif "indonesia" in league_slug.lower():
                country = "Indonesia"
            elif "malaysia" in league_slug.lower():
                country = "Malaysia"
            elif "singapore" in league_slug.lower():
                country = "Singapore"
            elif "thailand" in league_slug.lower():
                country = "Thailand"
            elif "vietnam" in league_slug.lower():
                country = "Vietnam"
            elif "india" in league_slug.lower():
                country = "India"
            elif "uae" in league_slug.lower():
                country = "UAE"
            elif "qatar" in league_slug.lower():
                country = "Qatar"
            elif "saudi" in league_slug.lower():
                country = "Saudi Arabia"
            elif "iran" in league_slug.lower():
                country = "Iran"
            elif "iraq" in league_slug.lower():
                country = "Iraq"
            elif "egypt" in league_slug.lower():
                country = "Egypt"
            elif "morocco" in league_slug.lower():
                country = "Morocco"
            elif "tunisia" in league_slug.lower():
                country = "Tunisia"
            elif "algeria" in league_slug.lower():
                country = "Algeria"
            elif "nigeria" in league_slug.lower():
                country = "Nigeria"
            elif "ghana" in league_slug.lower():
                country = "Ghana"
            elif "senegal" in league_slug.lower():
                country = "Senegal"
            elif "cameroon" in league_slug.lower():
                country = "Cameroon"
            elif "ivory_coast" in league_slug.lower():
                country = "Ivory Coast"
            elif "south_africa" in league_slug.lower():
                country = "South Africa"
            elif "argentina" in league_slug.lower():
                country = "Argentina"
            elif "brazil" in league_slug.lower():
                country = "Brazil"
            elif "colombia" in league_slug.lower():
                country = "Colombia"
            elif "chile" in league_slug.lower():
                country = "Chile"
            elif "peru" in league_slug.lower():
                country = "Peru"
            elif "ecuador" in league_slug.lower():
                country = "Ecuador"
            elif "uruguay" in league_slug.lower():
                country = "Uruguay"
            elif "paraguay" in league_slug.lower():
                country = "Paraguay"
            elif "bolivia" in league_slug.lower():
                country = "Bolivia"
            elif "venezuela" in league_slug.lower():
                country = "Venezuela"
            elif "mexico" in league_slug.lower():
                country = "Mexico"
            elif "costa_rica" in league_slug.lower():
                country = "Costa Rica"
            elif "panama" in league_slug.lower():
                country = "Panama"
            elif "guatemala" in league_slug.lower():
                country = "Guatemala"
            elif "honduras" in league_slug.lower():
                country = "Honduras"
            elif "el_salvador" in league_slug.lower():
                country = "El Salvador"
            elif "nicaragua" in league_slug.lower():
                country = "Nicaragua"
            elif "usa" in league_slug.lower() or "mls" in league_slug.lower():
                country = "USA"
                championship = "MLS"
            
            # Normalize championship name
            if "league one" in championship.lower():
                championship = "League One"
            elif "premier league" in championship.lower():
                championship = "Premier League"
            elif "championship" in championship.lower():
                championship = "Championship"
            elif "liga" in championship.lower() and "premier" not in championship.lower():
                if "2" in championship or "segunda" in championship.lower():
                    championship = "Division 2"
                else:
                    championship = championship.replace("Ligue 1", "Ligue 1").replace("Liga", "Liga")
            elif "bundesliga" in championship.lower():
                if "2" in championship:
                    championship = "2. Bundesliga"
                else:
                    championship = "Bundesliga"
            elif "serie" in championship.lower():
                championship = "Serie A"
            elif "eredivisie" in championship.lower():
                championship = "Eredivisie"
            elif "primeira" in championship.lower() or "liga portugal" in championship.lower():
                championship = "Liga Portugal"
            elif "super lig" in championship.lower():
                championship = "Süper Lig"
            elif "allsvenskan" in championship.lower():
                championship = "Allsvenskan"
            elif "eliteserien" in championship.lower():
                championship = "Eliteserien"
            elif "superliga" in championship.lower():
                championship = "Superliga"
            elif "challenge" in championship.lower():
                championship = "Challenge League"
            elif "premier league" in championship.lower():
                championship = "Premier League"
            
            # Extract team name from data
            team_name = data.get("team", {}).get("name", "Unknown")
            team_id = data.get("team", {}).get("id", "")
            team_slug = data.get("team", {}).get("slug", "")
            
            team_info = {
                "id": team_id,
                "name": team_name,
                "slug": team_slug
            }
            
            if country not in hierarchy:
                hierarchy[country] = {}
            if championship not in hierarchy[country]:
                hierarchy[country][championship] = []
            
            # Avoid duplicates
            if not any(t["id"] == team_id for t in hierarchy[country][championship]):
                hierarchy[country][championship].append(team_info)
                
        except Exception as e:
            print(f"Error loading {f}: {e}")
            continue
    
    return hierarchy

if __name__ == "__main__":
    hierarchy = build_lineup_hierarchy()
    print(json.dumps(hierarchy, indent=2, ensure_ascii=False))
