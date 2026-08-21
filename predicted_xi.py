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

def parse_round_matches(championship: str) -> List[Dict[str, Any]]:
    """Return every match in the currently-displayed jornada.

    futbolfantasy.com renders each match as a `.partido` link inside a
    `.jornada.jornadaN` wrapper. The CURRENT jornada is the only one
    whose wrapper has style="" (others have display:none applied
    by their jornada selector).

    Returns list of dicts:
        [{ff_id, slug, home, away, fecha, url}, ...]
    """
    url = CHAMPIONSHIPS.get(championship.lower())
    if not url:
        return []
    html = fetch(url)
    if not html:
        return []
    return _parse_matches_from_html(html)


def _parse_matches_from_html(html: str) -> List[Dict[str, Any]]:
    # Find each .jornada block with style="" (current).
    # Past rounds render as <div class="jornada jornadaN" style="display: none;">
    # so the leading "style=" (with empty value) marks the only active round.
    pattern = re.compile(
        r'<div[^>]*class="jornada jornada(\d+)"\s+style="">\s*'
        r'<a[^>]+href="https://www\.futbolfantasy\.com/partidos/(\d+)-([a-z0-9-]+)"[^>]*class="partido[^"]*"[^>]*>',
        re.DOTALL,
    )
    out = []
    seen = set()
    for m in pattern.finditer(html):
        jornada, ff_id, slug = m.group(1), m.group(2), m.group(3)
        if ff_id in seen:
            continue
        seen.add(ff_id)
        # Take window after this match, until next match anchor.
        start = m.end()
        next_m = pattern.search(html, start)
        end = next_m.start() if next_m else start + 4000
        block = html[start:end]
        # Tooltip lives on the opening <a class="partido"> tag.
        # m.start() points to "<div...", m.end() points just after the
        # closing '>' of the opening <a ...> tag. So html[m.start():m.end()]
        # contains the entire partido anchor opening tag with all attrs.
        partido_tag = html[m.start():m.end()]
        tooltip_m = re.search(r'data-tooltip="([^"]+)"', partido_tag)
        if tooltip_m:
            tt = tooltip_m.group(1).strip()
            # Tooltip format: "Home - Away" possibly with score
            # e.g. "Betis - Real Sociedad", "Rayo 1-1 Alavés",
            # "Valencia 2 - 1 Celta".
            # 1) Strip score pattern in the middle: "Home SCORE Away".
            score_m = re.search(r'\s+\d+\s*[-–]\s*\d+\s+', tt)
            if score_m:
                home = tt[:score_m.start()].strip()
                away = tt[score_m.end():].strip()
            elif ' - ' in tt:
                home, away = tt.split(' - ', 1)
                home = home.strip()
                away = away.strip()
            elif '-' in tt:
                # fallback single dash with possible spaces
                left, right = tt.split('-', 1)
                home = left.strip()
                away = right.strip()
            else:
                home, away = '', ''
        else:
            home, away = '', ''
        # fallback to img alt if tooltip parsing failed
        if not home:
            home_m = re.search(r'<img[^>]+class="escudo local[^"]*"[^>]*alt="([^"]+)"', block)
            home = home_m.group(1) if home_m else ''
        if not away:
            away_m = re.search(r'<img[^>]+class="escudo visitante[^"]*"[^>]*alt="([^"]+)"', block)
            away = away_m.group(1) if away_m else ''
        # fecha: e.g. "Jue 21:00h", or "Vie 21/08 <br>21:00h".
        fecha_m = re.search(r'<div class="fecha">\s*(?:([^<]*?)\s*<br>)?\s*([^<]+?)\s*</div>', block, re.DOTALL)
        if fecha_m:
            d = fecha_m.group(1) or ''
            t = fecha_m.group(2) or ''
            fecha = (d + ' ' + t).strip()
        else:
            fecha = ''
        out.append({
            'ff_id': ff_id,
            'slug': slug,
            'home': home,
            'away': away,
            'fecha': fecha,
            'url': f'https://www.futbolfantasy.com/partidos/{ff_id}-{slug}',
        })
    return out


def parse_match_xi(ff_id: str, slug: str, home_name: str = '', away_name: str = '') -> Dict[str, Any]:
    """Fetch a single match page and return 11 titular home + 11 titular away.

    futbolfantasy renders the predicted XI for both teams on the same page;
    the local (home) team appears first in the field/portero grid, the
    visiting (away) team second. We take only `data-onceFF="titular"` blocks
    and the FIRST truncate-name under each (in case alternatives are listed).

    Returns dict:
        {
          'home': [{'ff_name': 'Marc Roca', 'ff_id': '3215'}, ...11],
          'away': [{'ff_name': 'Remiro', 'ff_id': '1975'}, ...11]
        }
    """
    url = f'https://www.futbolfantasy.com/partidos/{ff_id}-{slug}'
    html = fetch(url)
    if not html:
        return {'home': [], 'away': []}

    # Find all titular blocks; each one contains a <span class="truncate-name">.
    # Use a non-greedy slice so the inner juggador block (which holds the name)
    # is captured as part of the same match.
    titular_re = re.compile(
        r'class="jugador_(\d+)\s+[^"]*"[^>]*data-onceFF="titular"(.*?)(?=class="jugador_\d+\s+[^"]*"|$)',
        re.DOTALL,
    )
    blocks = []
    for m in titular_re.finditer(html):
        jugador_id = m.group(1)
        body = m.group(2)
        name_m = re.search(r'<span class="truncate-name mx-auto">([^<]+)</span>', body)
        if name_m:
            blocks.append({'ff_id': jugador_id, 'ff_name': name_m.group(1).strip()})

    # Only first 22 = 11 home + 11 away.
    blocks = blocks[:22]
    return {'home': blocks[:11], 'away': blocks[11:]}


def normalise_name_match(ff_name: str, lv_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the LineupValue player whose name corresponds to ff_name.

    Futbolfantasy renders "FirstName Surname" (e.g. "Marc Roca").
    LineupValue uses "Surname FirstName" (e.g. "Roca Marc").

    Returns the matched LV player dict or None.
    """
    if not ff_name:
        return None
    ff_variants = set(name_variants(ff_name))
    # Score each LV player by how many variants match (substring or full).
    best = None
    best_score = 0
    for p in lv_players:
        lv_name = p.get('name') or ''
        lv_variants = name_variants(lv_name)
        # Try full-token match (the strongest signal).
        for v in lv_variants:
            if v in ff_variants:
                score = 3
                if score > best_score:
                    best_score = score
                    best = p
                break
        else:
            # Substring fallback: first token of one is prefix of the other.
            lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
            ff_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', ff_name) if t]
            if not lv_toks or not ff_toks:
                continue
            for lt in lv_toks:
                for ft in ff_toks:
                    if lt and ft and (lt.startswith(ft) or ft.startswith(lt)) and len(lt) >= 3 and len(ft) >= 3:
                        score = 1
                        if score > best_score:
                            best_score = score
                            best = p
                        break
    return best


# Phase 1.3-1.5 smoke test
if __name__ == '__main__':
    import sys
    champ = sys.argv[1] if len(sys.argv) > 1 else 'laliga'
    ms = parse_round_matches(champ)
    print(f'{champ}: {len(ms)} matches')
    for m in ms[:3]:
        xi = parse_match_xi(m['ff_id'], m['slug'], m['home'], m['away'])
        h = m['home']; a = m['away']; fid = m['ff_id']
        print(f'\n  {fid} {h} vs {a}')
        print(f'    home ({len(xi["home"])}): {[p["ff_name"] for p in xi["home"]]}')
        print(f'    away ({len(xi["away"])}): {[p["ff_name"] for p in xi["away"]]}')
