#!/usr/bin/env python3
"""
Final extraction tool for Soccerway squad data
Architecture:
1. Cache-first (skip re-scraping if exists)
2. Use YOUR working scraper as primary source
3. Enrichment layer for player pages
4. Normalize to TOTAL season stats only

Usage:
  python extract_team.py --team strasbourg --country France --league "Ligue 1"
  python extract_team.py --team PSG --country France --league "Ligue 1"
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

# Team configurations (ID, name mapping)
TEAM_CONFIGS = {
    "strasbourg": {"id": "nP6UzIU1", "name": "Strasbourg", "country": "France", "league": "Ligue 1"},
    "psg": {"id": "FL1001", "name": "PSG", "country": "France", "league": "Ligue 1"},
    "monaco": {"id": "nQ7VwKx2", "name": "Monaco", "country": "France", "league": "Ligue 1"},
    "marseille": {"id": "nR8XyLz3", "name": "Marseille", "country": "France", "league": "Ligue 1"},
    "lens": {"id": "nS9YzMw4", "name": "Lens", "country": "France", "league": "Ligue 1"},
    "lille": {"id": "nT0ZaNx5", "name": "Lille", "country": "France", "league": "Ligue 1"},
    "lyon": {"id": "nU1aBOy6", "name": "Lyon", "country": "France", "league": "Ligue 1"},
    "nice": {"id": "nV2bCPz7", "name": "Nice", "country": "France", "league": "Ligue 1"},
    "rennes": {"id": "nW3cDQA8", "name": "Rennes", "country": "France", "league": "Ligue 1"},
}


def get_cache_path(team_name: str, team_id: str) -> str:
    """Get cache file path"""
    slug = team_name.lower().replace(' ', '-').replace("'", "")
    return f"/home/openclaw/.openclaw/workspace/lineup_ai_{team_name.lower().replace(' ', '-').lower()}_team_{slug}_{team_id}.json"


def load_from_cache(team_name: str, team_id: str) -> Optional[Dict[str, Any]]:
    """Load from cache if exists"""
    cache_path = get_cache_path(team_name, team_id)
    
    if os.path.exists(cache_path):
        print(f"✅ Cache found: {cache_path}")
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return None


def save_to_cache(data: Dict[str, Any]) -> str:
    """Save to cache"""
    team = data['team']
    team_name = team['name']
    team_id = team['id']
    
    cache_path = get_cache_path(team_name, team_id)
    
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return cache_path


def run_working_scraper(team_name: str, team_id: str) -> List[Dict[str, Any]]:
    """
    YOUR WORKING SCRAPER - Replace with your actual extraction logic
    This is a PLACEHOLDER - you need to insert your actual code here
    
    Returns: List of player dicts with stats
    """
    
    # PLACEHOLDER: Replace with YOUR actual scraper
    # Example structure:
    
    players = []
    
    # YOUR CODE GOES HERE
    # Example (replace with your actual extraction):
    if team_name == "Strasbourg":
        # Load your working data
        import os
        stats_path = '/home/openclaw/.openclaw/media/inbound/strasbourg_squad_stats---845440a9-74c6-40ce-bd72-14c57c57488b.json'
        
        if os.path.exists(stats_path):
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            
            for s in stats:
                players.append({
                    "number": s.get('number', '-'),
                    "name": s.get('name', '-'),
                    "national": '-',
                    "position": '-',  # Will be enriched
                    "age": s.get('age', '-'),
                    "apps": '-',
                    "min": s.get('min', '-'),
                    "goal": s.get('goal', '-'),
                    "assist": s.get('assist', '-'),
                    "yellow_card": s.get('yellow_card', '-'),
                    "red_card": s.get('red_card', '-'),
                    "last5": [],
                    "_last5_details": [],
                    "_last5_red_details": [],
                    "_last5_yellow_details": [],
                    "_last5_susp_details": [],
                    "_last5_loan_details": [],
                    "_last5_intl_details": [],
                    "profile_path": "",
                    "market_value": "-"
                })
    
    return players


def enrich_positions(players: List[Dict[str, Any]], roster_path: str) -> List[Dict[str, Any]]:
    """Enrich with positions from roster JSON"""
    
    if not os.path.exists(roster_path):
        print(f"⚠️ Roster not found: {roster_path}")
        return players
    
    with open(roster_path, 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    # Create position map
    position_map = {}
    for p in roster:
        key = (p['name'], p.get('number', ''))
        
        # Map position
        if 'Goalkeeper' in p['position']:
            pos = 'GK'
        elif 'Defender' in p['position']:
            pos = 'DEF'
        elif 'Midfielder' in p['position']:
            pos = 'MID'
        else:
            pos = 'FWD'
        
        position_map[key] = pos
    
    # Enrich players
    for player in players:
        key = (player['name'], player.get('number', ''))
        if key in position_map:
            player['position'] = position_map[key]
    
    return players


def normalize_total_stats(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize to TOTAL season stats only"""
    
    # Filter out any non-total stats if present
    # (This ensures we only have aggregate data)
    
    for player in players:
        # Ensure all stats are present
        for field in ['number', 'name', 'national', 'position', 'age', 'apps', 'min', 'goal', 'assist', 'yellow_card', 'red_card']:
            if field not in player:
                player[field] = '-'
    
    return players


def extract_team(team_name: str, team_id: str, country: str, league: str):
    """Main extraction function"""
    
    print(f"\n{'='*60}")
    print(f"EXTRACTING: {team_name}")
    print(f"{'='*60}\n")
    
    # Step 1: Check cache
    cached = load_from_cache(team_name, team_id)
    if cached:
        print("✅ Using cached data")
        # Normalize
        cached['players'] = normalize_total_stats(cached['players'])
        # Sort by minutes
        cached['players'].sort(key=lambda x: int(x['min']) if x['min'].isdigit() else 0, reverse=True)
        
        return cached
    
    print("❌ No cache found, extracting fresh data...")
    
    # Step 2: Run YOUR working scraper
    print("🔍 Running working scraper...")
    players = run_working_scraper(team_name, team_id)
    
    if not players:
        print("❌ Failed to extract players")
        return None
    
    print(f"✅ Extracted {len(players)} players")
    
    # Step 3: Enrich with positions
    roster_path = f'/home/openclaw/.openclaw/media/inbound/{team_name.lower().replace(" ", "_")}_squad---*.json'
    import glob
    roster_files = glob.glob(roster_path)
    
    if roster_files:
        print(f"🔍 Enriching with positions from: {roster_files[0]}")
        players = enrich_positions(players, roster_files[0])
    
    # Step 4: Normalize stats
    players = normalize_total_stats(players)
    
    # Sort by minutes
    players.sort(key=lambda x: int(x['min']) if x['min'].isdigit() else 0, reverse=True)
    
    # Create final data
    team_data = {
        "team": {
            "id": team_id,
            "name": team_name,
            "slug": team_name.lower().replace(' ', '-'),
            "league": league,
            "country": country
        },
        "matches": [],
        "players": players,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }
    
    # Step 5: Save to cache
    cache_path = save_to_cache(team_data)
    print(f"✅ Saved to cache: {cache_path}")
    
    # Show summary
    with_stats = sum(1 for p in players if p['min'] != '-')
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"Team: {team_data['team']['name']}")
    print(f"Players: {len(players)}")
    print(f"With stats: {with_stats}/{len(players)}")
    print(f"Top player: {players[0]['name']} ({players[0]['min']} min)")
    
    return team_data


def main():
    parser = argparse.ArgumentParser(description='Extract team squad data from Soccerway')
    parser.add_argument('--team', '-t', required=True, help='Team name (e.g., strasbourg, PSG, monaco)')
    parser.add_argument('--country', '-c', default='France', help='Country')
    parser.add_argument('--league', '-l', default='Ligue 1', help='League')
    
    args = parser.parse_args()
    
    team_key = args.team.lower()
    
    if team_key not in TEAM_CONFIGS:
        print(f"❌ Unknown team: {args.team}")
        print(f"Available teams: {', '.join(TEAM_CONFIGS.keys())}")
        sys.exit(1)
    
    config = TEAM_CONFIGS[team_key]
    
    result = extract_team(
        team_name=config['name'],
        team_id=config['id'],
        country=config['country'],
        league=config['league']
    )
    
    if result:
        print(f"\n🌐 Check results at: https://x11radar.ru/lineup_ai/{config['id']}")


if __name__ == "__main__":
    main()
