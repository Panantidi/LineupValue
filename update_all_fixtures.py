#!/usr/bin/env python3
"""Update fixtures for all teams in cache."""
import asyncio
import json
import os
import sys
sys.path.insert(0, '/home/openclaw/FormAlert')

from fetch_team import get_fixtures_by_slug

CACHE_DIR = '/home/openclaw/.openclaw/workspace'

async def update_team_fixtures(team_id, team_name, team_slug):
    """Fetch and save fixtures for a single team."""
    cache_path = f'{CACHE_DIR}/_live_cache_{team_id}.json'
    
    try:
        # Fetch fixtures
        fixtures = await get_fixtures_by_slug(team_id, team_name, team_slug, limit=2)
        
        # Update cache
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                data = json.load(f)
            data['fixtures'] = fixtures
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return len(fixtures)
    except Exception as e:
        print(f'  ERROR {team_name}: {e}')
        return -1
    
    return 0

async def main():
    # Get all cache files
    cache_files = [f for f in os.listdir(CACHE_DIR) if f.startswith('_live_cache_') and f.endswith('.json')]
    total = len(cache_files)
    print(f'Updating fixtures for {total} teams...')
    
    updated = 0
    errors = 0
    empty = 0
    
    for i, cache_file in enumerate(cache_files, 1):
        team_id = cache_file.replace('_live_cache_', '').replace('.json', '')
        cache_path = f'{CACHE_DIR}/{cache_file}'
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            team_name = data.get('team', {}).get('name', team_id)
            team_slug = data.get('team', {}).get('slug', team_id.lower())
            
            print(f'[{i}/{total}] {team_name} ({team_id})...', end=' ', flush=True)
            
            count = await update_team_fixtures(team_id, team_name, team_slug)
            
            if count > 0:
                print(f'{count} fixtures')
                updated += 1
            elif count == 0:
                print('0 fixtures')
                empty += 1
            else:
                errors += 1
                
        except Exception as e:
            print(f'ERROR: {e}')
            errors += 1
        
        # Small delay to avoid rate limiting
        if i % 5 == 0:
            await asyncio.sleep(1)
    
    print(f'\nDone! Updated: {updated}, Empty: {empty}, Errors: {errors}')

if __name__ == '__main__':
    asyncio.run(main())