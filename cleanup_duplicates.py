#!/usr/bin/env python3
"""
Clean up duplicate teams from JSON files
Only keep teams that are in the hardcoded leagues_data.json
"""

import json
import glob
import os

HIERARCHY_FILE = "/home/openclaw/FormAlert/leagues_data.json"
DATA_DIR = "/home/openclaw/.openclaw/workspace"

def load_hardcoded_teams():
    """Load teams from hardcoded hierarchy"""
    with open(HIERARCHY_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    hardcoded_team_ids = set()
    for country, leagues in data.items():
        for league_name, teams in leagues.items():
            for team in teams:
                hardcoded_team_ids.add(team["id"])
    
    return hardcoded_team_ids

def cleanup_json_files():
    """Remove JSON files for duplicate teams"""
    hardcoded_ids = load_hardcoded_teams()
    
    files_to_delete = []
    files_to_keep = []
    
    for f in glob.glob(DATA_DIR + "/lineup_ai_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
            
            team_id = data.get("team", {}).get("id", "")
            
            if team_id in hardcoded_ids:
                files_to_keep.append(f)
            else:
                files_to_delete.append(f)
        
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    # Delete duplicates
    deleted = 0
    for f in files_to_delete:
        try:
            os.remove(f)
            deleted += 1
            print(f"Deleted: {os.path.basename(f)}")
        except Exception as e:
            print(f"Error deleting {f}: {e}")
    
    print(f"\n✅ Deleted {deleted} duplicate files")
    print(f"✅ Kept {len(files_to_keep)} files")
    
    return deleted

if __name__ == "__main__":
    print("=== Cleaning up duplicate teams ===\n")
    cleanup_json_files()
