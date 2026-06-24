#!/usr/bin/env python3
"""Refresh all teams from cache - runs hourly via cron."""
import os
import sys
import subprocess
import time
from pathlib import Path

CACHE_DIR = Path('/home/openclaw/.openclaw/workspace')
SCRIPT = '/home/openclaw/FormAlert/refresh_team_version.py'
LOG = '/tmp/refresh_all_teams.log'

def log(msg):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG, 'a') as f:
        f.write(line + '\n')

def get_all_teams():
    """Get all team IDs from cache files."""
    teams = []
    for f in CACHE_DIR.glob('_live_cache_*.json'):
        team_id = f.stem.replace('_live_cache_', '')
        teams.append(team_id)
    return teams

def refresh_team(team_id):
    """Refresh a single team."""
    try:
        result = subprocess.run(
            ['/home/openclaw/FormAlert/.venv/bin/python3', SCRIPT, team_id],
            capture_output=True,
            text=True,
            timeout=120,
            cwd='/home/openclaw/FormAlert'
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT refreshing {team_id}")
        return False
    except Exception as e:
        log(f"  ERROR refreshing {team_id}: {e}")
        return False

def main():
    log("=== Starting hourly refresh ===")
    teams = get_all_teams()
    log(f"Found {len(teams)} teams in cache")
    
    refreshed = 0
    for team_id in teams:
        if refresh_team(team_id):
            refreshed += 1
        # Small delay to avoid overwhelming Soccerway
        time.sleep(2)
    
    log(f"=== Done: {refreshed}/{len(teams)} teams refreshed ===")

if __name__ == '__main__':
    main()
