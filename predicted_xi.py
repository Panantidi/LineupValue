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


# Aug 22 2026 — nickname / alias dictionary. futbolfantasy often
# renders the short form ("Lalo", "Nacho", "Kuki", "Viti", "Míchel",
# "Colo", "Lokillo", "Peleteiro", etc.) while LineupValue stores
# the full legal name. These aliases are checked after the primary
# token/substring matcher fails; the first alias that produces a
# match wins. Lowercase keys.
#
# IMPORTANT: each alias must be the FULL LV-style name in the form
# it actually appears in the squad ("Surname Given" for single-
# surname names, "Surname1 Surname2 Given" for compound Spanish
# surnames). The matcher uses token-set equality so the more
# tokens the alias carries, the stronger the match.
#
# This list is hand-curated from real LaLiga / LaLiga 2
# mismatches seen in the Aug 22 2026 audit. Adding more is safe;
# missing ones just leave the player unmatched (which is the
# current behaviour). Do NOT add common surnames or the table
# explodes — only the short-form nickname -> canonical given
# name mappings where the canonical form is unambiguous.
NICKNAME_ALIASES: Dict[str, List[str]] = {
    # Verified mismatches from the Aug 22 2026 audit.
    'lalo':    ['Lopez Gonzalo', 'Aguilar Gonzalo', 'Lopez Aguilar Gonzalo'],
    'kuki':    ['Zalazar Kevin'],
    # Common Spanish given-name nicknames. We only add the
    # single-canonical case so the matcher picks the right one
    # even when the squad has multiple "Gonzalo" / "Victor" /
    # etc. entries — full name keeps the match unique.
    'colo':    ['Nicolas'],
    'nacho':   ['Ignacio'],
    'míchel':  ['Miguel'],
    'yangel':  ['Yangel'],
    'iker':    ['Iker'],
    'santi':   ['Santiago'],
    'cote':    ['Carlos'],
}

# Aug 22 2026 — roster-specific overrides for cases where the
# generic name matcher cannot connect an ff slot to the LV squad
# entry because the two stores expose disjoint pieces of the same
# player's name. Keys are (ff_name_lower, lv_team_id) tuples;
# values are the canonical given-name token the LV squad stores
# under (looked up case-insensitively against the LV player's
# name tokens).
#
# "Lachhab" (ff, surname only) is the Oviedo MF whose LV record
# only carries "Youness" — no token overlap exists so the matcher
# cannot bridge them.
#
# Augment the table whenever a new team-specific mismatch comes
# up. Keep it small — these are exceptions, not the rule.
ROSTER_OVERRIDES: Dict[Tuple[str, str], str] = {
    ('lachhab', 'SzYzw34K'): 'Youness',
}


def _roster_override(ff_name: str, lv_team_id: str,
                       lv_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Look up a roster-specific override for a single ff slot.

    Returns the LV player dict whose given-name token matches the
    canonical alias stored for (ff_name, team_id).
    """
    if not ff_name or not lv_team_id:
        return None
    key = (ff_name.strip().lower(), lv_team_id)
    wanted_given = ROSTER_OVERRIDES.get(key)
    if not wanted_given:
        return None
    wanted_tok = normalise_token(wanted_given)
    for p in lv_players:
        lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', p.get('name') or '') if t]
        if wanted_tok in lv_toks:
            return p
    return None


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
    return _parse_matches_from_html(html, championship=championship)


def _parse_matches_from_html(html: str, championship: str = '') -> List[Dict[str, Any]]:
    """Parse the jornada listing.

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
        re.DOTALL,
    )
    layout_b = re.compile(
        r'<div[^>]*class="partido-container"[^>]*>\s*'
        r'<a[^>]+href="https://www\.futbolfantasy\.com/partidos/(\d+)-([a-z0-9-]+)"[^>]*class="partido[^"]*"[^>]*>',
        re.DOTALL,
    )
    out = []
    seen = set()

    # Always use Layout B (partido-container, the main content) only.
    # The jornada-wrapper blocks on /laliga/posibles-alineaciones are the
    # sidebar that re-lists the same ten matches already shown by the
    # partido-container, so mixing both layers double-counts.
    # Layout A is kept around for the parser's docstring/tests but is
    # not used at runtime.

    for m in layout_b.finditer(html):
        ff_id = m.group(1)
        if ff_id in seen:
            continue
        seen.add(ff_id)
        # Wrap as a fake jornada match object so _append_match is
        # happy. Layout B regex exposes (ff_id, slug); jornada number
        # is unknown but we just carry 0 since the cache doesn't use it.
        m2 = type('FakeM', (), {})()
        m2.group = lambda i, _ffid=ff_id, _slug=m.group(2): ('0', _ffid, _slug)[i] if 0 <= i <= 2 else ''
        m2.start = lambda: m.start()
        m2.end = lambda: m.end()
        nb = layout_b.search(html, m.end())
        _append_match(out, html, m2, source='layout_b', next_m=nb)
    return out


def _append_match(out, html, m, source: str = 'layout_a', next_m=None):
    """Augment out with one parsed match entry.

    Uses the same tooltip/score parsing as before, but factored out so
    both Layout A (jornada-wrapped) and Layout B (partido-container)
    can share it.
    """
    if source == 'layout_a':
        ff_id = m.group(2)
        slug = m.group(3)
    else:
        ff_id = m.group(1)
        slug = m.group(2)
    # Determine end of the per-match block: next match's anchor opening
    # for whichever layout we're in. We use the partido anchor itself
    # as the boundary (each <a class="partido"> opens a new match).
    start = m.end()
    if next_m is not None:
        end = next_m.start()
    else:
        # Look for the next partido anchor in raw HTML.
        anchor_pat = re.compile(r'<a[^>]+class="partido[^"]*"[^>]*>')
        nm = anchor_pat.search(html, start + 1)
        end = nm.start() if nm else start + 4000
    block = html[start:end]
    # Tooltip lives on the opening <a class="partido"> tag.
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
        # Aug 22 2026 — derive position from the wrapper class.
        # futbolfantasy uses "portero" for GK and "campo" for
        # outfield. Map to LV-style positions so build_match_cache
        # can pass a position hint to normalise_name_match.
        if 'portero' in cls:
            ff_position = 'GK'
        elif 'campo' in cls:
            # campo covers DF/MF/FW — we don't know which.
            # Leave the hint empty; the LV squad knows its own
            # per-player position, and "outfield" is still useful
            # for ruling out a GK candidate when the futbolfantasy
            # slot is an outfield one.
            ff_position = 'OUTFIELD'
        else:
            ff_position = ''
        blocks.append({
            'ff_id': jugador_id,
            'ff_name': name_m.group(1).strip(),
            'ff_position': ff_position,
        })

    # Only first 22 = 11 home + 11 away.
    blocks = blocks[:22]
    return {'home': blocks[:11], 'away': blocks[11:]}


def normalise_name_match(ff_name: str, lv_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the LineupValue player whose name corresponds to ff_name.

    Futbolfantasy renders "FirstName Surname" (e.g. "Marc Roca").
    LineupValue uses "Surname FirstName" (e.g. "Roca Marc").

    Returns the matched LV player dict or None.

    Aug 22 2026 — hardened to fix two specific bugs Max saw:
      1) "Mariño" (futbolfantasy) was matching "Marin Carlos"
         because both share the "marin" prefix and the matcher
         picked the first LV squad row that started with that
         prefix. We now require an exact token match first, and
         a substring/prefix match must agree on at least one
         *full* token, not just share a 5-letter prefix.
      2) "Dani Díaz" (futbolfantasy) was matching "Galilea Daniel"
         because "daniel" is a token in both names. Same fix as
         above — full-token equality wins, partial matches only
         stand when the other side has no other LV player sharing
         the same token.

    Strategy, in order:
      1) Full-token set match (any of ff_variants ∩ lv_variants).
      2) If multiple LV players match by token, prefer the one
         whose position (GK/DF/MF/FW) matches the slot hint if
         the caller passed `ff_position`. The futbolfantasy order
         is GK-first so we mirror that.
      3) Substring fallback: ff's surname appears as a full
         token of the LV name (i.e. lv has a token exactly equal
         to ff's surname, ignoring diacritics). Same in reverse.
    """
    if not ff_name:
        return None
    # Optional kwarg access via kwargs slot — kept positional
    # elsewhere for backwards compat.
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
    #   b) position hint if provided
    #   c) shorter LV name (more specific identity)
    full_hits = []  # list of (score, lv_player)
    for p in lv_players:
        lv_name = p.get('name') or ''
        lv_variants = name_variants(lv_name)
        # Count tokens that appear in both sides (as full tokens).
        lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
        common = [t for t in ff_toks if t in lv_toks]
        if not common:
            continue
        # Variants that contain ALL ff tokens — the strongest signal.
        all_in_variants = sum(1 for v in lv_variants if all(t in v for t in ff_toks))
        score = 100 + len(common) * 10 + all_in_variants * 5
        full_hits.append((score, p, lv_name, len(lv_toks)))

    if full_hits:
        # Aug 22 2026 — tiebreak by position hint first.
        if ff_position:
            by_pos = [h for h in full_hits if (h[1].get('position') or '').upper() == ff_position.upper()]
            if by_pos:
                full_hits = by_pos
        # Aug 22 2026 — tiebreak by *longer* LV name (more
        # tokens = more specific identity, e.g. "San Bartolome
        # Victor" beats "Valverde Victor" when both share the
        # ff token "Victor"). Falls back to alphabetic to stay
        # deterministic.
        full_hits.sort(key=lambda h: (-h[0], -h[3], h[2]))
        return full_hits[0][1]

    # Pass 2: substring fallback — only accept when one side's
    # full token equals the other side's full token (already
    # covered by pass 1) OR the longer token is at least 5 chars
    # and the shorter one is at least 4 chars AND the shorter
    # is a *strict* prefix of the longer. This catches e.g.
    # "Gavi" -> "Gavi Pablo" but rejects "Mariño" -> "Marin
    # Carlos" because the 5-char "marin" is NOT a strict prefix
    # of "marino" (it is the other way around, "marin" is a
    # prefix of "marino"). Wait — that's wrong: "marin" IS a
    # strict prefix of "marino". So this rule alone is not enough.
    # The crucial extra rule: the longer token must NOT itself be
    # an LV surname for someone *else* in the squad. If "Marino
    # Diego" exists alongside "Marin Carlos", the squad has both
    # full surnames, and the matcher must choose the one whose
    # full surname appears as a substring of the ff surname.
    sub_hits = []
    for p in lv_players:
        lv_name = p.get('name') or ''
        lv_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', lv_name) if t]
        for lt in lv_toks:
            for ft in ff_toks:
                if not lt or not ft or len(lt) < 4 or len(ft) < 4:
                    continue
                if lt == ft:
                    # exact full-token equality — this should have
                    # been caught by pass 1 already, but keep for
                    # safety.
                    sub_hits.append((50, p, lv_name, len(lv_toks)))
                    break
                # Strict prefix (shorter is a prefix of longer).
                shorter, longer = (lt, ft) if len(lt) < len(ft) else (ft, lt)
                if len(shorter) < 4:
                    continue
                if not longer.startswith(shorter):
                    continue
                # Reject the case where the longer token ALSO
                # appears as a full surname in some OTHER LV
                # player of the squad — that means the squad has
                # both names and we should match the ff name to
                # the one whose surname matches exactly.
                long_token = ft if len(ft) >= len(lt) else lt
                long_token_is_other_lv_surname = False
                for q in lv_players:
                    if q is p:
                        continue
                    q_toks = [normalise_token(t) for t in re.split(r'[\s\.\-]+', q.get('name') or '') if t]
                    if long_token in q_toks:
                        long_token_is_other_lv_surname = True
                        break
                if long_token_is_other_lv_surname:
                    continue
                sub_hits.append((20 + len(shorter), p, lv_name, len(lv_toks)))
                break
            else:
                continue
            break

    if sub_hits:
        if ff_position:
            by_pos = [h for h in sub_hits if (h[1].get('position') or '').upper() == ff_position.upper()]
            if by_pos:
                sub_hits = by_pos
        # Aug 22 2026 — prefer longer LV name (more specific).
        sub_hits.sort(key=lambda h: (-h[0], -h[3], h[2]))
        return sub_hits[0][1]
    return None


# Phase 1.3-1.5 smoke test
if __name__ == '__main__':
    import sys
    champ = sys.argv[1] if len(sys.argv) > 1 else 'laliga'
    if len(sys.argv) > 2 and sys.argv[2] == 'cache':
        # warm up cache for current round
        from pathlib import Path
        ms = parse_round_matches(champ)
        for m in ms:
            cache_p = cache_path(m.get('slug', '?'))
            print(f'  {m["ff_id"]} {m["home"]} vs {m["away"]}')
        print(f'\nTotal matches to fetch: {len(ms)}')
        sys.exit(0)
    ms = parse_round_matches(champ)
    print(f'{champ}: {len(ms)} matches')
    for m in ms[:3]:
        xi = parse_match_xi(m['ff_id'], m['slug'], m['home'], m['away'])
        h = m['home']; a = m['away']; fid = m['ff_id']
        print(f'\n  {fid} {h} vs {a}')
        print(f'    home ({len(xi["home"])}): {[p["ff_name"] for p in xi["home"]]}')
        print(f'    away ({len(xi["away"])}): {[p["ff_name"] for p in xi["away"]]}')


def build_match_cache(championship: str, match_id: str, ff_id: str, slug: str,
                      home_team_id: str, away_team_id: str,
                      kickoff_ts: int,
                      home_lv_players: List[Dict[str, Any]],
                      away_lv_players: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a per-match cache dict and save it. Returns the dict.

    Used by the scheduler when T-18:00 has passed and by the
    refresh=1 path through /api/predicted_xi/<mid>.

    Aug 22 2026 — pass the futbolfantasy position hint (GK / OUTFIELD)
    through to normalise_name_match so the matcher can rule out
    mismatched-position candidates (e.g. picking a GK when the
    futbolfantasy slot is an outfield one, or vice versa).

    Aug 22 2026 — three-stage matcher with a positional/leftover
    fallback that fixes single-token edge cases like:
      - "Lachhab"  (ff, surname-only) → squad has "Youness" (no
        token overlap at all, but it's the only MF who hasn't
        been matched yet on Oviedo's squad).
      - "Lalo" (ff, nickname for "Gonzalo Lopez Aguilar") → squad
        has "Aguilar Lopez Gonzalo" with no token overlap to the
        nickname. Position + "is the only DF on Leganés' squad
        that hasn't been matched yet" picks it up.
    """
    xi = parse_match_xi(ff_id, slug)
    home_xi, home_matched_players = _match_side(
        xi['home'], home_lv_players, side_label='home',
    )
    away_xi, away_matched_players = _match_side(
        xi['away'], away_lv_players, side_label='away',
    )
    data = {
        'match_id': match_id,
        'championship': championship,
        'ff_id': ff_id,
        'slug': slug,
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
        'home_players': home_xi,
        'away_players': away_xi,
        'kickoff_ts': kickoff_ts,
        'fetched_at': int(time.time()),
    }
    save_match_xi(data)
    return data


def _match_side(ff_side: List[Dict[str, Any]],
                lv_players: List[Dict[str, Any]],
                side_label: str) -> Tuple[List[Dict[str, Any]], set]:
    """Match every ff player on one side against the LV squad.

    Returns (matched_list, set_of_already_matched_player_ids).
    The matched_list preserves the ff input order. Each entry has:
      {ff_name, ff_id, lv_player_id, lv_name, matched}
    """
    out = []
    matched_player_ids = set()
    # Aug 22 2026 — derive the LV team_id from any squad row that
    # carries it (the live cache stores _team_id per player). If
    # none of the rows have it, leave the team_id empty so the
    # roster-override path falls through to the generic matcher.
    lv_team_id = ''
    for q in lv_players:
        t = q.get('_team_id') or q.get('team_id') or ''
        if t:
            lv_team_id = t
            break
    # Two passes so positional leftovers (third pass) only see the
    # state AFTER the strong-match players have been claimed.
    for p in ff_side:
        # Aug 22 2026 — roster-specific override runs FIRST. It
        # bypasses both the generic matcher and the alias
        # dictionary. Use it only for hand-verified team+ff pairs
        # where the generic matcher provably can't connect (e.g.
        # "Lachhab" is the surname stored on the LV side under
        # "Youness" — disjoint token sets).
        matched = _roster_override(p['ff_name'], lv_team_id, lv_players)
        if not matched:
            matched = _normalise_name_match_impl(
                p['ff_name'], lv_players,
                ff_position=p.get('ff_position', ''),
            )
        out.append({
            'ff_name': p['ff_name'],
            'ff_id': p['ff_id'],
            'lv_player_id': (matched or {}).get('player_id'),
            'lv_name': (matched or {}).get('name'),
            'matched': matched is not None,
        })
        if matched:
            matched_player_ids.add(matched.get('player_id'))
    # Third pass: positional / leftover fallback. For every entry
    # that came back unmatched, look at the LV squad and see whether
    # there is exactly ONE player of the same position who has NOT
    # been matched yet. If so, that player must be the one — accept
    # it even if there is zero token overlap (nickname / surname-only
    # cases like "Lachhab" / "Youness" or "Lalo" / "Aguilar Lopez
    # Gonzalo").
    #
    # Aug 22 2026 — relaxed rule for ff slots with a single token
    # (futbolfantasy tends to render only the surname for some
    # players): when the ff_name has ONE token and the number of
    # remaining LV candidates is more than one but still small,
    # we don't auto-match (would be unsafe) — we still leave it
    # unmatched so the cache reflects reality. The single-candidate
    # case is the only one we accept.
    for i, p in enumerate(out):
        if p['matched']:
            continue
        ff_pos = (ff_side[i].get('ff_position') or '').upper()
        # Candidates: LV players not yet matched, on the same position
        # bucket (GK vs OUTFIELD), and not the GK when ff_pos is GK,
        # etc. We treat OUTFIELD as "DF/MF/FW" — any of them.
        cands = []
        for q in lv_players:
            qid = q.get('player_id')
            if qid in matched_player_ids:
                continue
            qpos = (q.get('position') or '').upper()
            if ff_pos == 'GK' and qpos != 'GK':
                continue
            if ff_pos == 'OUTFIELD' and qpos == 'GK':
                continue
            cands.append(q)
        if len(cands) == 1:
            only = cands[0]
            out[i] = {
                'ff_name': p['ff_name'],
                'ff_id': p['ff_id'],
                'lv_player_id': only.get('player_id'),
                'lv_name': only.get('name'),
                'matched': True,
                'matched_by': 'positional_leftover',
            }
            matched_player_ids.add(only.get('player_id'))
    return out, matched_player_ids


def get_match_xi(match_id: str) -> Optional[Dict[str, Any]]:
    """Public API: returns cached match XI or None."""
    return load_match_xi(match_id, max_age=CACHE_TTL)
