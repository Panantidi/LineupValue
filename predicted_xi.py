"""Spain LaLiga/LaLiga 2 Predicted XI fetcher.

Aug 22 2026.

Parses futbolfantasy.com (https://www.futbolfantasy.com/laliga/posibles-alineaciones
and /laliga2/posibles-alineaciones) to pull the predicted XI for each
upcoming match, normalises player names to LineupValue's "Surname FirstName"
format, and caches per-match results so the T-18 cron can pre-warm them.

Per-match cache:
    _predicted_xi_<match_id>.json

Schema:
    {
      "match_id": "jFuzhjVI", "ff_id": "22441", "slug": "betis-real-sociedad",
      "home_team_id": "vJbTeCGP", "away_team_id": "jNvak2f3",
      "home_players": [{"ff_name": "...", "lv_player_id": "...", "lv_name": "..."},
                       ...],
      "away_players": [...],
      "fetched_at": <epoch>, "kickoff_ts": <epoch>
    }

Used by:
    - app.py   (scheduler + /api/predicted_xi endpoints)
    - compare_template.html (autopxi=1)
"""
import re
import time
import json
import os
import unicodedata
import urllib.request
import urllib.error
from typing import List, Dict, Optional, Tuple, Any

CACHE_DIR = '/home/openclaw/.openclaw/workspace'
CACHE_PREFIX = '_predicted_xi_'
CACHE_TTL = 6 * 3600  # 6 hours — re-parse if older

DEFAULT_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
)

# Championship slug -> futbolfantasy URL fragment
CHAMPIONSHIPS = {
    'laliga':   'https://www.futbolfantasy.com/laliga/posibles-alineaciones',
    'laliga2':  'https://www.futbolfantasy.com/laliga2/posibles-alineaciones',
}


def fetch(url: str, timeout: int = 30) -> Optional[str]:
    """HTTP GET with browser UA. Returns text or None on failure."""
    req = urllib.request.Request(url, headers={'User-Agent': DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        return None


def cache_path(match_id: str) -> str:
    return os.path.join(CACHE_DIR, f'{CACHE_PREFIX}{match_id}.json')


def load_match_xi(match_id: str, max_age: int = CACHE_TTL) -> Optional[Dict[str, Any]]:
    p = cache_path(match_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    fetched_at = data.get('fetched_at') or 0
    if max_age and (time.time() - fetched_at) > max_age:
        return None
    return data


def save_match_xi(data: Dict[str, Any]) -> None:
    p = cache_path(data['match_id'])
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def normalise_token(t: str) -> str:
    """Lowercase + strip diacritics + remove non-alphanumerics."""
    t = unicodedata.normalize('NFD', t)
    t = t.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', t.lower())


def name_variants(name: str) -> List[str]:
    """All tokenisations of a player name we should match.

    "Marc Roca" -> ['marc roca', 'roca marc']
    "L. Sucic"  -> ['l sucic', 'sucic l', 'lsucic', 'sucicl']
    """
    parts = [p for p in re.split(r'[\s\.\-]+', name.strip()) if p]
    if not parts:
        return []
    out = set()
    out.add(' '.join(parts))
    if len(parts) >= 2:
        out.add(' '.join(reversed(parts)))
    # 1-word fallback
    if len(parts) == 1:
        out.add(parts[0])
    # joined forms
    out.add(''.join(parts))
    if len(parts) >= 2:
        out.add(''.join(reversed(parts)))
    return [normalise_token(v) for v in out if v]