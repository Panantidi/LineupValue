"""Spain LaLiga/LaLiga 2 Predicted XI fetcher + Italy Serie A.

Aug 22 2026 — Spain.
Aug 29 2026 — Added Italy Serie A (sport.sky.it).

Parses futbolfantasy.com for Spain and sport.sky.it for Italy,
normalises player names to LineupValue's "Surname FirstName" format,
and caches per-match results so the T-18 cron can pre-warm them.

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

# Championship slug -> source URL
# Spain: futbolfantasy.com
# Italy: sport.sky.it
CHAMPIONSHIPS = {
    'laliga':   'https://www.futbolfantasy.com/laliga/posibles-alineaciones',
    'laliga2':  'https://www.futbolfantasy.com/laliga2/posibles-alineaciones',
    'seriea':   'https://sport.sky.it/calcio/serie-a/probabili-formazioni',
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
    if not name:
        return []
    toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', name) if t]
    toks = [t for t in toks if t]
    if not toks:
        return []
    out = set()
    out.add(' '.join(toks))
    out.add(' '.join(reversed(toks)))
    if len(toks) == 2:
        out.add(toks[0] + toks[1])
        out.add(toks[1] + toks[0])
    return list(out)


# --- Nickname / alias expansion for Spanish first names ---
# futbolfantasy uses short forms that have zero token overlap with
# the LV full name. We expand these before matching.
NICKNAME_ALIASES: Dict[str, List[str]] = {
    'nacho': ['ignacio'],
    'lalo': ['gonzalo'],
    'colo': ['nicolas'],
    'mikel': ['miguel'],
    'marcos': ['marco'],
    'kike': ['enrique'],
    'dani': ['daniel'],
    'pepe': ['jose'],
    'paco': ['francisco'],
    'tete': ['alberto'],
    'juanmi': ['juan miguel'],
    'alex': ['alejandro'],
    'javi': ['javier'],
    'sergi': ['sergio'],
    'gabi': ['gabriel'],
    'victor': ['victor'],
    'pablo': ['pablo'],
    'rafa': ['rafael'],
    'moi': ['moises'],
    'isak': ['isaac'],
    'luis': ['luis'],
    'carlos': ['carlos'],
    'marco': ['marco'],
    'ivan': ['ivan'],
    'chupete': ['chupe'],
}


def parse_round_matches(championship: str, jornada: int = 0, url: str = '') -> List[Dict[str, Any]]:
    """Return every match in the displayed jornada/round.

    Spain (laliga/laliga2): futbolfantasy.com
    Italy (seriea): sport.sky.it
    """
    championship_lower = championship.lower()
    
    if championship_lower in ('laliga', 'laliga2'):
        return _parse_round_matches_spain(championship_lower, jornada, url)
    elif championship_lower == 'seriea':
        return _parse_round_matches_italy(jornada, url)
    return []


def _parse_round_matches_spain(championship: str, jornada: int = 0, url: str = '') -> List[Dict[str, Any]]:
    """Parse futbolfantasy.com for LaLiga / LaLiga 2."""
    fetch_url = url or CHAMPIONSHIPS.get(championship)
    if not fetch_url:
        return []
    if jornada and not url:
        fetch_url = f'https://www.futbolfantasy.com/{championship}/posibles-alineaciones/{jornada}'
    if jornada:
        html = fetch(fetch_url)
        if not html:
            return []
        return _parse_matches_from_html(html, championship=championship, include_all_jornadas=True)
    html = fetch(fetch_url)
    if not html:
        return []
    return _parse_matches_from_html(html, championship=championship)


def _parse_round_matches_italy(giornata: int = 0, url: str = '') -> List[Dict[str, Any]]:
    """Parse sport.sky.it for Serie A round (giornata)."""
    if not url:
        url = CHAMPIONSHIPS['seriea']
    
    html = fetch(url)
    if not html:
        return []
    
    # The main page has a link to the current round page.
    # Extract it and fetch that page instead.
    round_url = _extract_round_url(html)
    if round_url:
        html = fetch(round_url)
        if not html:
            return []
    
    return _parse_matches_from_sky_html(html, round_url, giornata)


def _extract_round_url(html: str) -> Optional[str]:
    """Extract the round-specific probabili-formazioni URL from the main page."""
    import re
    m = re.search(r'href="([^"]*probabili-formazioni-serie-a-giornata[^"]*)"', html)
    if m:
        return m.group(1)
    return None


def _parse_matches_from_sky_html(html: str, round_url: str, giornata: int = 0) -> List[Dict[str, Any]]:
    """Parse the round-specific page which contains all match cards with formations.
    
    Returns list of dicts: [{ff_id, slug, home, away, date, time, url}, ...]
    """
    import re
    
    # Find all h2 tags with their positions
    h2_pattern = re.compile(r'<h2>([^<]+)</h2>')
    h2_positions = [(m.start(), m.group(1).strip()) for m in h2_pattern.finditer(html)]
    
    matches = []
    
    for i, (h2_pos, title) in enumerate(h2_positions):
        # Skip non-match h2 tags
        if title in ('Introduzione', 'Leggi anche'):
            continue
        
        # Find the next h2 position to bound the card
        next_h2_pos = h2_positions[i + 1][0] if i + 1 < len(h2_positions) else len(html)
        card_html = html[h2_pos:next_h2_pos]
        
        # Parse title: "Milan-Venezia, venerdì ore 20:45"
        if ',' not in title:
            continue
        teams_part = title.split(',')[0].strip()
        date_time_part = title.split(',', 1)[1].strip()
        
        # Split home - away
        if ' - ' in teams_part:
            home_name, away_name = [s.strip() for s in teams_part.split(' - ', 1)]
        elif '-' in teams_part:
            home_name, away_name = [s.strip() for s in teams_part.split('-', 1)]
        else:
            continue
        
        # Find "Probabili formazioni" section
        pf_idx = card_html.find('Probabili formazioni')
        if pf_idx == -1:
            continue
        formations_text = card_html[pf_idx:]
        
        # Extract predicted XI for both teams
        home_players = _extract_sky_formation(formations_text, home_name)
        away_players = _extract_sky_formation(formations_text, away_name)
        
        # Generate a stable ff_id from team names
        ff_id = f"sky_{home_name.lower().replace(' ', '-')}-{away_name.lower().replace(' ', '-')}"
        slug = f"{home_name.lower().replace(' ', '-')}-{away_name.lower().replace(' ', '-')}"
        
        matches.append({
            'ff_id': ff_id,
            'slug': slug,
            'home': home_name,
            'away': away_name,
            'date': date_time_part,
            'url': round_url,
            'home_players_raw': home_players,
            'away_players_raw': away_players,
        })
    
    return matches


def _extract_sky_formation(text: str, team_name: str) -> List[str]:
    """Extract player names for a team from the formations text.
    
    Handles two patterns:
    1. <b>Team (formation):</b> player1; player2; ...
    2. <b>Team</b> <b>(formation)</b>: player1; player2; ...
    """
    import re
    team_escaped = re.escape(team_name)
    
    # Pattern 1: formation inside same <b> tag
    pattern1 = rf"<b[^>]*>\s*{team_escaped}\s*(?:\([^)]+\))?\s*:?\s*</b>\s*([^<]+)"
    match = re.search(pattern1, text, re.IGNORECASE)
    
    # Pattern 2: formation in separate <b> tag
    if not match or (match and not match.group(1).strip()):
        pattern2 = rf"<b[^>]*>\s*{team_escaped}\s*</b>\s*<b[^>]*>\([^)]+\)</b>\s*:\s*([^<]+)"
        match = re.search(pattern2, text, re.IGNORECASE)
    
    if not match or not match.group(1).strip():
        return []
    
    players_str = match.group(1)
    raw_players = re.split(r'[;,]', players_str)
    
    cleaned = []
    for p in raw_players:
        p = p.strip()
        if not p:
            continue
        # Remove jersey numbers, positions, etc.
        p = re.sub(r'\s*\(\d+\)', '', p)  # remove (10) etc
        p = re.sub(r'^\d+\.\s*', '', p)   # remove leading "1. "
        p = p.strip()
        if p:
            cleaned.append(p)
    
    return cleaned[:11]


def _parse_matches_from_html(html: str, championship: str = '', include_all_jornadas: bool = False) -> List[Dict[str, Any]]:
    """Parse the jornada listing from futbolfantasy.com.

    Two layouts to handle, both served by futbolfantasy.com:

    Layout A (LaLiga 1st division, /laliga/posibles-alineaciones) —
    each match wrapped in
        <div class="jornada jornadaN" style="">
            <a class="partido ..." href="...partidos/<id>-<slug>" ...>
    Past rounds use style="display: none;" so an empty `style=""`
    marks the only currently-active round.

    Layout B (LaLiga 2nd division, /laliga2/posibles-alineaciones) —
    no jornada wrappers, matches live directly inside
        <div class="partido-container">
            <a class="partido ..." href="...partidos/<id>-<slug>" ...>
    There is also a sidebar with the LaLiga 1 schedule still using
    the jornada-wrapper shape — we want the LaLiga 2 match list
    only, so when `championship == 'laliga2'` we ONLY use Layout B.

    The `championship` arg lets callers pick the right layout
    explicitly. When empty (default) we keep both for backwards
    compatibility with the very first test paths.
    """
    layout_a = re.compile(
        r'<div[^>]*class="jornada jornada(\d+)"\s+style="">\s*'
        r'<a[^>]+href="https://www\.futbolfantasy\.com/partidos/(\d+)-([a-z0-9-]+)"[^>]*class="partido[^"]*"[^>]*>',
    )
    layout_b = re.compile(
        r'<div[^>]*class="partido-container"[^>]*>\s*'
        r'<a[^>]+href="https://www\.futbolfantasy\.com/partidos/(\d+)-([a-z0-9-]+)"[^>]*class="partido[^"]*"[^>]*>',
    )

    matches = []

    if championship == 'laliga2':
        # Only layout B
        for m in layout_b.finditer(html):
            ff_id = m.group(1)
            slug = m.group(2)
            home, away, fecha = _extract_match_info_from_slug(html, m.start())
            if home and away:
                matches.append({'ff_id': ff_id, 'slug': slug, 'home': home, 'away': away, 'fecha': fecha})
    else:
        # LaLiga 1 or unknown: try layout A first (current jornada only)
        for m in layout_a.finditer(html):
            jornada_num = int(m.group(1))
            ff_id = m.group(2)
            slug = m.group(3)
            home, away, fecha = _extract_match_info_from_slug(html, m.start())
            if home and away:
                matches.append({'ff_id': ff_id, 'slug': slug, 'home': home, 'away': away, 'fecha': fecha, 'jornada': jornada_num})

        if not matches and not include_all_jornadas:
            # Fallback to layout B
            for m in layout_b.finditer(html):
                ff_id = m.group(1)
                slug = m.group(2)
                home, away, fecha = _extract_match_info_from_slug(html, m.start())
                if home and away:
                    matches.append({'ff_id': ff_id, 'slug': slug, 'home': home, 'away': away, 'fecha': fecha})

        if include_all_jornadas:
            # Also parse hidden jornadas for neighbouring round lookup
            hidden_jornada = re.compile(
                r'<div[^>]*class="jornada jornada(\d+)"\s+style="display:\s*none;"[^>]*>\s*'
                r'<a[^>]+href="https://www\.futbolfantasy\.com/partidos/(\d+)-([a-z0-9-]+)"[^>]*class="partido[^"]*"[^>]*>',
            )
            for m in hidden_jornada.finditer(html):
                jornada_num = int(m.group(1))
                ff_id = m.group(2)
                slug = m.group(3)
                home, away, fecha = _extract_match_info_from_slug(html, m.start())
                if home and away:
                    matches.append({'ff_id': ff_id, 'slug': slug, 'home': home, 'away': away, 'fecha': fecha, 'jornada': jornada_num})

    return matches


def _extract_match_info_from_slug(html: str, start_pos: int) -> Tuple[str, str, str]:
    """Extract home/away/fecha from the partido link context."""
    # Look backwards/forwards from the link for team names and date
    context = html[max(0, start_pos - 500):start_pos + 500]
    home = away = fecha = ''
    
    # Try to find team names in data-tooltip attribute
    tooltip_match = re.search(r'data-tooltip="([^"]*)"', context)
    if tooltip_match:
        tooltip = tooltip_match.group(1)
        # Format: "Home - Away" or "Home - Away" with scores
        if ' - ' in tooltip:
            parts = tooltip.split(' - ')
            home = parts[0].strip()
            away = parts[1].strip()
            # Remove scores if present (e.g., "Racing 3-2 Elche" -> "Racing" and "Elche")
            home = re.sub(r'\s+\d+-\d+$', '', home)
            away = re.sub(r'^\d+-\d+\s+', '', away)
        elif '-' in tooltip:
            parts = tooltip.split('-')
            home = parts[0].strip()
            away = parts[1].strip()
            home = re.sub(r'\s+\d+-\d+$', '', home)
            away = re.sub(r'^\d+-\d+\s+', '', away)
    
    # Try to find fecha
    fecha_match = re.search(r'<div class="fecha">([^<]+)</div>', context)
    if fecha_match:
        fecha = fecha_match.group(1).strip()
    
    return home, away, fecha


def parse_match_xi(ff_id: str, slug: str, home_name: str = '', away_name: str = '') -> Dict[str, Any]:
    """Fetch a single match page and return 11 titular home + 11 titular away.
    
    Dispatches based on the championship inferred from ff_id prefix:
    - "sky_" -> sport.sky.it
    - numeric -> futbolfantasy.com (Spain)
    """
    if ff_id.startswith('sky_'):
        return parse_match_xi_sky(ff_id, slug, home_name, away_name)
    else:
        return parse_match_xi_spain(ff_id, slug, home_name, away_name)


def parse_match_xi_spain(ff_id: str, slug: str, home_name: str = '', away_name: str = '') -> Dict[str, Any]:
    """Fetch a single match page from futbolfantasy and return 11 titular home + 11 titular away."""
    url = f'https://www.futbolfantasy.com/partidos/{ff_id}-{slug}'
    html = fetch(url)
    if not html:
        return {'home': [], 'away': []}

    titular_re = re.compile(
        r'class="jugador_(\d+)\s+([^"]+)"[^>]*data-onceFF="titular"(.*?)(?=class="jugador_\d+\s+[^"]*"|$)',
        re.DOTALL,
    )
    blocks = []
    for m in titular_re.finditer(html):
        jugador_id = m.group(1)
        cls = m.group(2) or ''
        body = m.group(3)
        name_m = re.search(r'<span class="truncate-name mx-auto">([^<]+)</span>', body)
        if not name_m:
            continue
        if 'portero' in cls:
            ff_position = 'GK'
        elif 'campo' in cls:
            ff_position = 'OUTFIELD'
        else:
            ff_position = ''
        blocks.append({
            'ff_id': jugador_id,
            'ff_name': name_m.group(1).strip(),
            'ff_position': ff_position,
        })

    blocks = blocks[:22]
    return {'home': blocks[:11], 'away': blocks[11:]}


def parse_match_xi_sky(ff_id: str, slug: str, home_name: str = '', away_name: str = '') -> Dict[str, Any]:
    """Fetch predicted XI from sport.sky.it for Serie A.
    
    Uses the round-specific page which contains all formations.
    If home_name/away_name are empty, derive them from ff_id
    (build_match_cache passes empty names — ff_id is like "sky_napoli-como").
    """
    if not home_name or not away_name:
        parts = (ff_id or slug or '').replace('sky_', '').split('-')
        if len(parts) >= 2:
            home_name = home_name or parts[0]
            away_name = away_name or parts[1]
    # The main page has only a link to the round-specific page — fetch that instead
    url = CHAMPIONSHIPS['seriea']
    html = fetch(url)
    if not html:
        return {'home': [], 'away': []}

    round_url = _extract_round_url(html)
    if round_url:
        html = fetch(round_url)
        if not html:
            return {'home': [], 'away': []}
    
    # Reuse the reliable round-page parser (h2-positions approach)
    all_matches = _parse_matches_from_sky_html(html, round_url or url)
    
    for m in all_matches:
        h_name = m.get('home', '')
        a_name = m.get('away', '')
        
        if _names_match(h_name, home_name) and _names_match(a_name, away_name):
            home_players = m.get('home_players_raw', [])
            away_players = m.get('away_players_raw', [])
            
            # Convert to same format as Spain
            home_blocks = [{'ff_name': p, 'ff_id': f'sky_{i}', 'ff_position': 'GK' if i == 0 else 'OUTFIELD'} 
                          for i, p in enumerate(home_players)]
            away_blocks = [{'ff_name': p, 'ff_id': f'sky_{i}', 'ff_position': 'GK' if i == 0 else 'OUTFIELD'} 
                          for i, p in enumerate(away_players)]
            
            return {'home': home_blocks[:11], 'away': away_blocks[:11]}
    
    return {'home': [], 'away': []}


def _names_match(name1: str, name2: str) -> bool:
    """Fuzzy match team names."""
    if not name1 or not name2:
        return False
    n1 = normalise_token(name1)
    n2 = normalise_token(name2)
    return n1 == n2 or n1 in n2 or n2 in n1


def normalise_name_match(ff_name: str, lv_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the LineupValue player whose name corresponds to ff_name.

    Futbolfantasy renders "FirstName Surname" (e.g. "Marc Roca").
    LineupValue uses "Surname FirstName" (e.g. "Roca Marc").

    Returns the matched LV player dict or None.
    """
    if not ff_name:
        return None
    return _normalise_name_match_impl(ff_name, lv_players)


def _normalise_name_match_impl(ff_name: str, lv_players: List[Dict[str, Any]],
                                ff_position: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not ff_name:
        return None
    # Aug 22 2026 — nickname / alias expansion step. futbolfantasy
    # uses short forms ("Lalo", "Nacho", "Colo", "Mikel", "Marcos",
    # etc.) that have zero token overlap with the LV full name
    # ("Aguilar Lopez Gonzalo", "Vidal Nacho", "Marcos Alonso",
    # etc.). We expand the ff_name into a list of canonical
    # Spanish first-name aliases and rerun the matcher against
    # each alias. The first match wins.
    aliases = NICKNAME_ALIASES.get(ff_name.strip().lower(), [])
    candidates_to_try = [ff_name] + [a for a in aliases if a != ff_name]
    for name in candidates_to_try:
        hit = _normalise_name_match_impl_inner(name, lv_players, ff_position)
        if hit:
            return hit
    return None


def _normalise_name_match_impl_inner(ff_name: str, lv_players: List[Dict[str, Any]],
                                       ff_position: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not ff_name:
        return None
    ff_variants = set(name_variants(ff_name))
    ff_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', ff_name) if t]
    ff_toks = [t for t in ff_toks if t]

    # Pass 1: full-token match across any variant of either side.
    # Score by how many token-pairs agree, and tiebreak by:
    #   a) more tokens agreed (longer names are more specific)
    #   b) position match if ff_position given
    best = None
    best_score = (-1, -1)

    for p in lv_players:
        lv_name = p.get('name') or ''
        if not lv_name:
            continue
        lv_variants = set(name_variants(lv_name))
        common = ff_variants & lv_variants
        if not common:
            continue
        score = (len(common), sum(len(c) for c in common))
        if ff_position:
            lv_pos = (p.get('position') or '').upper()
            if ff_position == 'GK' and lv_pos == 'GK':
                score = (score[0] + 10, score[1])
            elif ff_position == 'OUTFIELD' and lv_pos != 'GK':
                score = (score[0] + 1, score[1])
        if score > best_score:
            best_score = score
            best = p

    if best:
        return best

    # Pass 1b (Aug 30 2026) — token-set match: the same tokens in ANY
    # order (reversed or permuted name order). Handles LV's
    # "Surname FirstName" vs ff's "FirstName Surname" even when the
    # name_variants permutations don't line up (e.g. 3-token names).
    ff_tok_set = set(ff_toks)
    if len(ff_toks) >= 2:
        for p in lv_players:
            lv_name = p.get('name') or ''
            if not lv_name:
                continue
            lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
            if set(lv_toks) == ff_tok_set:
                best = p
                break
    if best:
        return best

    # Pass 2: substring fallback — ff's surname as full token of LV name
    ff_surname_tok = ff_toks[-1] if ff_toks else ''
    if ff_surname_tok:
        for p in lv_players:
            lv_name = p.get('name') or ''
            lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
            if ff_surname_tok in lv_toks:
                return p

    # Pass 3: reverse — LV surname as full token of ff name
    for p in lv_players:
        lv_name = p.get('name') or ''
        lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
        lv_surname_tok = lv_toks[-1] if lv_toks else ''
        if lv_surname_tok and lv_surname_tok in ff_toks:
            return p

    return None


def _try_split_merged(ff_name: str, lv_players: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Try splitting a merged ff entry into two players.

    Aug 30 2026 — Sky sometimes merges two adjacent player names into
    one entry ("Politano Hojlund" = Politano + Højlund). Split at each
    token boundary; if both parts match distinct LV players, return
    two matched entries.
    """
    toks = [t for t in re.split(r'[\s\.\-]+', ff_name) if t]
    for i in range(1, len(toks)):
        p1, p2 = ' '.join(toks[:i]), ' '.join(toks[i:])
        m1 = normalise_name_match(p1, lv_players)
        if not m1:
            continue
        m2 = normalise_name_match(
            p2, [x for x in lv_players if x.get('player_id') != m1.get('player_id')])
        if m2:
            return [
                {
                    'ff_name': p1,
                    'ff_id': None,
                    'lv_player_id': m1.get('player_id'),
                    'lv_name': m1.get('name'),
                    'matched': True,
                    'matched_by': 'split',
                    'ff_position': None,
                },
                {
                    'ff_name': p2,
                    'ff_id': None,
                    'lv_player_id': m2.get('player_id'),
                    'lv_name': m2.get('name'),
                    'matched': True,
                    'matched_by': 'split',
                    'ff_position': None,
                },
            ]
    return None


def _match_by_number(number: str, lv_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Aug 30 2026 — number fallback: find the LV player by shirt number
    when the name match fails. Only used when the source provides
    shirt numbers (Serie A / Sky does not, LaLiga sources may)."""
    if not number:
        return None
    num = str(number).strip()
    if not num.isdigit():
        return None
    for p in lv_players:
        if str(p.get('number') or '').strip() == num:
            return p
    return None


def _match_one_with_split(ff_name: str, lv_players: List[Dict[str, Any]],
                          ff_position: Optional[str] = None,
                          ff_number: str = '') -> List[Dict[str, Any]]:
    """Match one ff entry, splitting merged player names when needed.

    If the whole-name match leaves ff tokens uncovered (the matched LV
    player's name doesn't contain all ff tokens), the entry is likely
    two merged players — try the split.
    """
    def _entry(lv_player: Optional[Dict[str, Any]], matched_by: Optional[str]) -> Dict[str, Any]:
        return {
            'ff_name': ff_name,
            'ff_id': None,
            'lv_player_id': (lv_player or {}).get('player_id'),
            'lv_name': (lv_player or {}).get('name'),
            'matched': bool(lv_player),
            'matched_by': matched_by,
            'ff_position': ff_position,
        }

    lv_player = normalise_name_match(ff_name, lv_players)
    if not lv_player:
        # Aug 30 2026 — number fallback: when the source provides shirt
        # numbers and the name match fails, match by number.
        by_number = _match_by_number(ff_number, lv_players)
        if by_number:
            return [_entry(by_number, 'number')]
        parts = _try_split_merged(ff_name, lv_players)
        if parts:
            for e in parts:
                e['ff_position'] = ff_position
            return parts
        return [_entry(None, None)]

    # Coverage check: are all ff tokens present in the matched player?
    ff_toks = set(normalise_token(t) for t in re.split(r'[\s\.\-]+', ff_name) if t)
    matched_toks = set(
        normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_player.get('name') or '') if t)
    if not ff_toks - matched_toks:
        return [_entry(lv_player, 'name')]

    # Suspicious merge — try splitting into two players.
    parts = _try_split_merged(ff_name, lv_players)
    if parts:
        for e in parts:
            e['ff_position'] = ff_position
        return parts
    return [_entry(lv_player, 'name')]


def build_match_cache(
    championship: str,
    match_id: str,
    ff_id: str,
    slug: str,
    home_team_id: str,
    away_team_id: str,
    kickoff_ts: int,
    home_lv_players: List[Dict[str, Any]],
    away_lv_players: List[Dict[str, Any]],
    home_name: str = '',
    away_name: str = '',
) -> Dict[str, Any]:
    """Fetch predicted XI, match to LV squads, write per-match cache.

    Returns the cache dict (also saved to disk).
    """
    # Fetch predicted XI (dispatches to Spain or Italy based on ff_id)
    xi = parse_match_xi(ff_id, slug, home_name=home_name, away_name=away_name)
    home_xi = xi.get('home', [])
    away_xi = xi.get('away', [])

    # Match home
    home_matched = []
    matched_player_ids = set()
    for p in home_xi:
        for e in _match_one_with_split(p.get('ff_name', ''), home_lv_players,
                                       p.get('ff_position'), p.get('number', '')):
            home_matched.append(e)
            if e.get('lv_player_id'):
                matched_player_ids.add(e.get('lv_player_id'))

    # Match away (separate matched set)
    away_matched = []
    matched_away_ids = set()
    for p in away_xi:
        for e in _match_one_with_split(p.get('ff_name', ''), away_lv_players,
                                       p.get('ff_position'), p.get('number', '')):
            away_matched.append(e)
            if e.get('lv_player_id'):
                matched_away_ids.add(e.get('lv_player_id'))

    cache = {
        'match_id': match_id,
        'ff_id': ff_id,
        'slug': slug,
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
        'home_players': home_matched,
        'away_players': away_matched,
        'fetched_at': int(time.time()),
        'kickoff_ts': kickoff_ts,
        'championship': championship,
    }
    save_match_xi(cache)
    return cache


def get_match_xi(match_id: str) -> Optional[Dict[str, Any]]:
    """Public API: returns cached match XI or None."""
    return load_match_xi(match_id, max_age=CACHE_TTL)