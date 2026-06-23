#!/usr/bin/env python3
"""Cron script: Check matches that finished 60+ minutes ago and refresh teams.

Run every 30 minutes via cron:
*/30 * * * * /home/openclaw/FormAlert/.venv/bin/python /home/openclaw/FormAlert/refresh_finished_matches.py >> /tmp/refresh_matches.log 2>&1
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path('/home/openclaw/.openclaw/workspace')
LOCK_DIR = Path('/tmp')
REFRESH_SCRIPT = Path('/home/openclaw/FormAlert/refresh_team_version.py')
LOG_FILE = Path('/tmp/refresh_matches.log')

# Minimum minutes after match end before refresh
MINUTES_AFTER_MATCH = 60


def log(msg):
    timestamp = datetime.now().isoformat()
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')


def get_all_team_caches():
    """Get all team cache files."""
    caches = []
    for f in CACHE_DIR.glob('_live_cache_*.json'):
        team_id = f.stem.replace('_live_cache_', '')
        caches.append((team_id, f))
    return caches


def parse_kickoff(kickoff_str):
    """Parse kickoff string to datetime."""
    if not kickoff_str:
        return None
    try:
        # Format: "2024-05-17T21:00"
        dt = datetime.strptime(kickoff_str, '%Y-%m-%dT%H:%M')
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None


def is_refresh_running(team_id):
    """Check if refresh is already running for this team."""
    lock_file = LOCK_DIR / f"formalert_refresh_{team_id}.lock"
    if not lock_file.exists():
        return False
    # Check if lock is stale (> 30 min old)
    if time.time() - lock_file.stat().st_mtime > 1800:
        lock_file.unlink()
        return False
    return True


def refresh_team(team_id):
    """Trigger refresh for a team."""
    if is_refresh_running(team_id):
        log(f"  Skip {team_id}: refresh already running")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, str(REFRESH_SCRIPT), team_id],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            log(f"  Refreshed {team_id}")
            return True
        else:
            log(f"  Error refreshing {team_id}: {result.stderr}")
            return False
    except Exception as e:
        log(f"  Exception refreshing {team_id}: {e}")
        return False


def main():
    import time
    
    log("=== Starting refresh_finished_matches ===")
    
    now = datetime.now(timezone.utc)
    refreshed = 0
    
    for team_id, cache_file in get_all_team_caches():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            matches = data.get('matches', [])
            if not matches:
                continue
            
            # Check first match (most recent)
            match = matches[0]
            kickoff_str = match.get('kickoff', '')
            
            if not kickoff_str:
                # No kickoff time, skip
                continue
            
            kickoff = parse_kickoff(kickoff_str)
            if not kickoff:
                continue
            
            # Match end time = kickoff + 90 minutes (standard match duration)
            match_end = kickoff + timedelta(minutes=90)
            
            # Check if match ended 60+ minutes ago
            time_since_end = now - match_end
            
            if time_since_end >= timedelta(minutes=MINUTES_AFTER_MATCH):
                # Also check if match was in the last 6 hours (don't refresh old matches)
                if time_since_end < timedelta(hours=6):
                    log(f"Team {team_id}: match ended {int(time_since_end.total_seconds()/60)} min ago, refreshing...")
                    if refresh_team(team_id):
                        refreshed += 1
                else:
                    log(f"Team {team_id}: match ended {int(time_since_end.total_seconds()/3600)} hours ago, skipping (too old)")
                    
        except Exception as e:
            log(f"Error processing {team_id}: {e}")
    
    log(f"=== Done: {refreshed} teams refreshed ===")
    return refreshed


if __name__ == '__main__':
    main()
