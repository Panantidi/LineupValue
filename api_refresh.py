"""On-demand refresh from Flashscore API (no Soccerway).
Refreshes squad + last 3 matches + lineups + player_details for a team.
"""
import json
import os
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- Config ---
KEY = "82f1fc4f2emsh6f172ea91bb5386p1cd344jsndd0fc401e69f"
HOST = "flashscore4.p.rapidapi.com"
HEADERS = {
    "X-Rapidapi-Key": KEY,
    "X-Rapidapi-Host": HOST,
    "User-Agent": "curl/8.5.0",
    "Accept": "*/*",
}
CACHE_DIR = "/home/openclaw/.openclaw/workspace"
LEAGUES_FILE = "/home/openclaw/FormAlert/leagues_data.json"

# --- Cache TTL ---
# --- Per-section TTL (Jul 23 2026) ---
# Different data has different update frequency:
# - Squad (transfers, ages) changes rarely -- refresh weekly
# - Player details (MV, photos) changes even more rarely -- refresh monthly
# - Last 3 results (matches + lineups) change after every game -- refresh daily
# - Fixtures (next 5 upcoming) change after each match -- refresh daily
CACHE_TTL_SECONDS = 600  # 10 minutes (overall default, used for is_fresh())
SQUAD_TTL_SECONDS = 7 * 86400      # 7 days
PLAYER_DETAILS_TTL_SECONDS = 30 * 86400  # 30 days
RESULTS_TTL_SECONDS = 86400        # 1 day
FIXTURES_TTL_SECONDS = 86400       # 1 day

# --- Lock to prevent concurrent refreshes for the same team ---
_refresh_in_progress = set()

# --- Slug cache (populated lazily) ---
_slug_cache = {}

# --- Coach side-channel (populated by refresh_squad, read by refresh_team) ---
# Jul 25 2026: /teams/squad returns coach in a "Coach" group separate from
# the player positions. refresh_squad writes coach_data here, refresh_team
# reads it and writes to cache["coach"]. Dict (not list) because the value
# itself is a dict {name, nationality} and dict.update is cleaner than list
# mutation.
_last_squad_coach = {"data": None}


def _get_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch(url, retries=2):
    """Fetch URL with retry. Returns dict/list or None."""
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=_get_ssl(), timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.3)
    return None


def _cache_path(team_id):
    return os.path.join(CACHE_DIR, f"_live_cache_{team_id}.json")


def _read_cache(team_id):
    """Read existing cache, or empty dict if missing/corrupt."""
    p = _cache_path(team_id)
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(team_id, data):
    """Write cache atomically."""
    p = _cache_path(team_id)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.rename(tmp, p)


_slug_cache = {}


def _verify_slug_via_api(team_id: str, slug: str) -> bool:
    """Hit /teams/details with the given slug and report whether it
    actually points to this team.

    Jul 24 2026: when leagues_data.json has the wrong slug (e.g. 'oviedo'
    for Real Oviedo, where the working slug is 'real-oviedo'),
    /teams/details returns an empty list 200. We use this fact to
    detect a stale slug without making the user click refresh
    twice. The /teams/details endpoint returns:
      - dict with team_id == our id   -> slug is correct
      - dict with team_id != our id   -> slug belongs to a different team
      - []                             -> slug is wrong (no such team page)
      - other (error, etc)             -> treat as inconclusive
    Returns True only if API confirms the slug resolves to OUR team_id.
    """
    try:
        from urllib.parse import quote
        url = f"https://{HOST}/api/flashscore/v2/teams/details?team_url=%2Fteam%2F{quote(slug, safe='')}%2F{team_id}%2F"
        d = _fetch(url, retries=1)
        if isinstance(d, dict) and d.get('team_id') == team_id:
            return True
        return False
    except Exception:
        return False


def _try_discover_slug(team_id: str) -> str | None:
    """Last-resort fallback: try several likely slug patterns.

    Jul 24 2026: when leagues_data.json has the wrong slug (e.g. 'oviedo'
    instead of 'real-oviedo'), the user gets a 502. As of this commit
    we don't blindly trust the stored slug — _get_team_info() now
    verifies it via API first. But if leagues_data.json is missing
    the team entirely (or has an empty slug), we still need ONE
    working URL. The patterns below cover the common cases:

      - team_id as slug:                /team/{id}/{id}/
      - lowercase team name:            /team/{name}/{id}/
      - lowercase team name with '-'s:  /team/{name-with-dashes}/{id}/
      - lowercase team name (no spaces): /team/{namenoslash}/{id}/

    Each pattern is tested by /teams/details. The first one whose
    response has team_id == our id wins. None if all fail.

    Note: this is a brute-force fallback and costs N extra API
    calls (typically 2-4) per team on the first refresh after
    a stale slug. After it succeeds, the discovered slug is
    cached in _slug_cache so subsequent refreshes are free.
    """
    from urllib.parse import quote
    patterns = [team_id]
    # Try common slug patterns. The team name is in the cache file
    # (already refreshed once) or leagues_data.json. We try both.
    name_candidates = []
    try:
        cache = _read_cache(team_id)
        if cache and (cache.get('team') or {}).get('name'):
            name_candidates.append((cache['team']['name']))
    except Exception:
        pass
    try:
        with open(LEAGUES_FILE) as f:
            ld = json.load(f)
        for country, champs in ld.items():
            for champ, teams in champs.items():
                for t in teams:
                    if t.get('id') == team_id and t.get('name'):
                        name_candidates.append(t['name'])
                        break
    except Exception:
        pass

    for name in name_candidates:
        n = name.strip()
        patterns.append(n)                          # 'Real Oviedo'
        patterns.append(n.lower())                  # 'real oviedo'
        patterns.append(n.lower().replace(' ', '-'))   # 'real-oviedo'
        patterns.append(n.lower().replace(' ', ''))    # 'realoviedo'
        # 'Dundee Utd' <-> 'Dundee United' swap (common shorthand)
        if 'utd' in n.lower():
            patterns.append(n.lower().replace('utd', 'united'))
        if 'united' in n.lower():
            patterns.append(n.lower().replace('united', 'utd'))

    seen = set()
    patterns = [p for p in patterns if p and not (p in seen or seen.add(p))]

    for slug in patterns:
        try:
            url = f"https://{HOST}/api/flashscore/v2/teams/details?team_url=%2Fteam%2F{quote(slug, safe='')}%2F{team_id}%2F"
            d = _fetch(url, retries=1)
            if isinstance(d, dict) and d.get('team_id') == team_id:
                return slug
        except Exception:
            continue
    return None


def _get_team_info(team_id):
    """Find team info in leagues_data.json. Returns (country, champ, slug) or None.

    Jul 24 2026 (bugfix): Real Oviedo / Dundee Utd were returning a
    False slug from leagues_data.json (e.g. 'oviedo' instead of
    'real-oviedo'), which caused /teams/details to return [] and the
    whole refresh to fail with 502. The new behavior is:

      1. Look up team in leagues_data.json (fast path, ~99% of calls)
      2. If found but slug field is missing/empty, treat as no slug
      3. If found WITH a slug, verify it via API. If it doesn't
         resolve to our team_id, log a warning and fall through.
      4. If the entry doesn't exist OR the slug didn't verify, try
         one last fallback: use team_id as slug (works for the
         ~5% of teams missing from leagues_data.json).
      5. If everything fails, return None (caller bails out).
    """
    if team_id in _slug_cache:
        return _slug_cache[team_id]
    try:
        with open(LEAGUES_FILE) as f:
            ld = json.load(f)
    except Exception:
        return None
    candidate = None
    for country, champs in ld.items():
        for champ, teams in champs.items():
            for t in teams:
                if t.get("id") == team_id:
                    candidate = (country, champ, t.get("slug") or "")
                    break
            if candidate:
                break
        if candidate:
            break
    if candidate:
        country, champ, slug = candidate
        if slug and _verify_slug_via_api(team_id, slug):
            info = (country, champ, slug)
            _slug_cache[team_id] = info
            return info
        # Slug present but stale. Don't trust it.
        if slug:
            print(f'[slug] stale slug {slug!r} for {team_id} ({country}/{champ}); trying fallback')
    # Last-resort: try team_id as slug
    fallback = _try_discover_slug(team_id)
    if fallback:
        # We don't know country/champ but we have a working slug.
        info = ('?', '?', fallback)
        _slug_cache[team_id] = info
        return info
    _slug_cache[team_id] = None
    return None


def _cache_age_seconds(team_id):
    """Return age of cache in seconds, or None if no cache."""
    p = _cache_path(team_id)
    if not os.path.exists(p):
        return None
    try:
        return time.time() - os.path.getmtime(p)
    except Exception:
        return None


def _section_age_seconds(team_id, section_name):
    """Return age of a specific section in seconds, or None if missing.

    Jul 23 2026: per-section TTL for delta refresh. Tracks each
    section's last-update timestamp in the cache file.

    Jul 23 2026 (bugfix, after revert to 4ee98a7): when
    section_last_updated[section_name] is missing (never set OR
    explicitly deleted), this function previously fell back to
    returning cache_age (the file mtime). That was wrong: a
    freshly refreshed cache file where section_last_updated was
    wiped would have mtime=0s, so any missing section would
    appear "fresh" and be silently skipped. Now missing sections
    return None, which makes _section_is_fresh() return False
    (forcing the API call).
    """
    p = _cache_path(team_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        su = data.get('section_last_updated', {})
        ts = su.get(section_name)
        if not ts:
            return None  # never refreshed, treat as stale
        dt = datetime.fromisoformat(ts)
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return None


def _section_is_fresh(team_id, section_name, ttl_seconds):
    """True if section age < ttl. None age (never refreshed) -> False."""
    age = _section_age_seconds(team_id, section_name)
    if age is None:
        return False
    return age < ttl_seconds


def _mark_section_updated(team_id, section_name):
    """Stamp section_last_updated[section_name] = now()."""
    try:
        cache = _read_cache(team_id) or {}
        su = cache.get('section_last_updated', {})
        su[section_name] = datetime.now().isoformat()
        cache['section_last_updated'] = su
        _write_cache(team_id, cache)
    except Exception as e:
        print(f'[delta] WARN: could not mark {section_name} updated: {e}')


def is_fresh(team_id, ttl=CACHE_TTL_SECONDS):
    """Return True if cache is fresh (age < TTL)."""
    age = _cache_age_seconds(team_id)
    if age is None:
        return False
    return age < ttl


def refresh_squad(team_id, slug, info, force=False):
    """Fetch /teams/squad and return parsed players list (or None).

    Jul 22 2026 — Senior Python Flask refactor (cache-driven architecture):
    Squad data MUST be taken from the "Total" group (aggregated across
    ALL competitions the team played in: league + cup + UEFA + friendlies),
    NOT from the first non-empty group (which was historically the
    top-tier league tab and missed cup / UEFA / friendly minutes).

    Why "Total" matters:
    - The user sees every player who ever appeared for the team
    - Last 3 START/SUB coverage is complete (not just league-only)
    - Stats (apps, min, goals, assists) are season-totals, not per-tournament

    Fallback chain:
    1. tab_name == "Total"        (preferred — verified Jul 2026 on 1607+ teams)
    2. tab_name case-insensitive  ("total", "TOTAL" — defensive)
    3. First non-empty group      (rare — some lower-division teams)
    """
    # Delta refresh (Jul 23 2026): skip API call if squad is fresh.
    # Jul 23 2026 (user feedback, after revert to 4ee98a7): force=True
    # should NOT bypass the section TTL. The user clicked ♻️ Refresh
    # twice in a row and observed API calls firing on the second
    # click. Now: force=True only bypasses the outer 10-min is_fresh()
    # guard; per-section TTLs (1d/30d/...) are always enforced.
    if _section_is_fresh(team_id, 'squad', SQUAD_TTL_SECONDS):
        cache = _read_cache(team_id)
        cached_players = (cache or {}).get('players', [])
        if cached_players:
            print(f'[delta] squad fresh, reusing {len(cached_players)} cached players (0 API calls)')
            return list(cached_players)
    url = f"https://{HOST}/api/flashscore/v2/teams/squad?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    data = _fetch(url)
    if not data:
        # Jul 24 2026: previously returned None here, which made
        # refresh_team bail out with 502 (the UI showed ❌ HTTP 502).
        # The actual cause was that the RapidAPI host returns []
        # (an empty list, HTTP 200) for teams whose squad data is
        # not yet in their database — e.g. Genclerbirligi. This is
        # NOT a transient error, it's a permanent "no squad data
        # for this team" answer, so we return [] (empty player
        # list) and let the team page render with no player table
        # rather than failing the entire refresh.
        if data == []:
            return []
        return None
    groups = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(groups, list) or not groups:
        return []
    players = []

    # Pick the right group. Priority: exact "Total" → case-insensitive → first non-empty.
    best_group = None
    for g in groups:
        if isinstance(g, dict) and g.get("tab_name") == "Total" and g.get("list"):
            best_group = g
            break
    if not best_group:
        for g in groups:
            if isinstance(g, dict) and str(g.get("tab_name", "")).strip().lower() == "total" and g.get("list"):
                best_group = g
                break
    if not best_group:
        # Fallback for lower-division squads that only have one tab
        for g in groups:
            if isinstance(g, dict) and g.get("list"):
                best_group = g
                break

    if best_group:
        tab_name = best_group.get("tab_name", "Total")
        coach_data = None  # Jul 25 2026: capture Coach from same squad group
        for section in best_group["list"]:
            if not isinstance(section, dict):
                continue
            grp_name = section.get("name", "")
            # Jul 25 2026: extract coach from Coach section BEFORE skipping.
            # The API returns coach in a separate group named "Coach" with one
            # player entry. Previously skipped with no replacement.
            if str(grp_name).strip().lower() == "coach":
                for cp in section.get("players", []) or []:
                    if not isinstance(cp, dict):
                        continue
                    coach_data = {
                        "name": cp.get("name", "").strip(),
                        "nationality": cp.get("country_name", "").strip(),
                    }
                    break
                continue
            for p in section.get("players", []):
                pid = p.get("player_id")
                name = p.get("name")
                if not pid or not name:
                    continue
                # Strip trailing reason keywords (e.g. "Vindahl Peter Foot Injury" → "Vindahl Peter")
                name = _strip_missing_reason_suffix(name)
                country = p.get("country_name", "")
                players.append({
                    "player_id": pid,
                    "name": name,
                    "position": _map_position(grp_name),
                    "position_raw": grp_name,  # preserve original (debugging / fallback)
                    "age": _clean_cell(p.get("age")),
                    "nationality": country,
                    "country": country,
                    "country_flag": _country_to_flag(country),
                    "number": p.get("number"),
                    "market_value": _clean_cell(None),  # filled by player_details
                    "matches_played": int(p["matches_played"]) if p.get("matches_played", "").isdigit() else 0,
                    "minutes_played": int(p["minutes_played"]) if p.get("minutes_played", "").isdigit() else 0,
                    "goals": int(p["goals_scored"]) if p.get("goals_scored", "").isdigit() else 0,
                    "assists": int(p["assists"]) if p.get("assists", "").isdigit() else 0,
                    "yellow_cards": int(p["yellow_cards"]) if p.get("yellow_cards", "").isdigit() else 0,
                    "red_cards": int(p["red_cards"]) if p.get("red_cards", "").isdigit() else 0,
                    "player_url": p.get("player_url", ""),
                    "tournament": tab_name,
                })
    # Jul 25 2026: attach coach_data as a side-channel return value
    # (caller in refresh_team() reads it and writes to cache["coach"]).
    # Stash on a module-level list so the tuple stays simple.
    _last_squad_coach["data"] = coach_data
    return players


# --- Normalize empty cells ---
# Jul 22 2026 — Senior Python Flask refactor.
# Cache used to store None for missing Age / Market Value. The UI rendered
# "None" as literal text. We now return "" so the template can render an
# empty <td></td> cleanly. The contract:
#     None         → ""     (was None)
#     ""           → ""     (already empty)
#     "–", "—", "?", "N/A" → ""  (placeholder chars also become empty)
#     "23"         → 23     (numeric coercion when possible)
#     "€5.2M"      → "€5.2M" (preserve formatted strings)
def _clean_cell(value):
    """Normalize a single cell value to '' (empty) or its real content.

    Used for Age, Market Value, and any other optional field where the
    template should render an empty cell instead of "None" / "–" / "?".
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if value == 0 or value != value:  # 0 or NaN
            return ""
        return value
    s = str(value).strip()
    if not s:
        return ""
    # Treat placeholder chars as empty
    if s in ("–", "—", "-", "?", "N/A", "n/a", "none", "None", "null", "NULL"):
        return ""
    # Try numeric coercion
    if s.isdigit():
        return int(s)
    try:
        return float(s)
    except ValueError:
        return s


# --- Country → flag URL ---
# Mirrors phase2_generic.COUNTRY_CODES (Jul 2026 snapshot).
# Verified against flagcdn.com — all 80+ entries resolve to real PNGs.
_COUNTRY_CODES = {
    "afghanistan": "af", "albania": "al", "algeria": "dz", "andorra": "ad",
    "angola": "ao", "argentina": "ar", "armenia": "am", "australia": "au",
    "austria": "at", "azerbaijan": "az", "bahrain": "bh", "bangladesh": "bd",
    "belarus": "by", "belgium": "be", "bolivia": "bo", "bosnia and herzegovina": "ba",
    "bosnia": "ba", "brazil": "br", "bulgaria": "bg", "cambodia": "kh",
    "cameroon": "cm", "canada": "ca", "chile": "cl", "china": "cn",
    "colombia": "co", "costa rica": "cr", "croatia": "hr", "cuba": "cu",
    "cyprus": "cy", "czech republic": "cz", "czechia": "cz", "denmark": "dk",
    "dominican republic": "do", "ecuador": "ec", "egypt": "eg", "el salvador": "sv",
    "england": "gb-eng", "estonia": "ee", "ethiopia": "et", "finland": "fi",
    "france": "fr", "gabon": "ga", "georgia": "ge", "germany": "de",
    "ghana": "gh", "gibraltar": "gi", "greece": "gr", "guatemala": "gt",
    "honduras": "hn", "hong kong": "hk", "hungary": "hu", "iceland": "is",
    "india": "in", "indonesia": "id", "iran": "ir", "iraq": "iq",
    "ireland": "ie", "israel": "il", "italy": "it", "ivory coast": "ci",
    "jamaica": "jm", "japan": "jp", "jordan": "jo", "kazakhstan": "kz",
    "kenya": "ke", "kosovo": "xk", "kuwait": "kw", "latvia": "lv",
    "lebanon": "lb", "lithuania": "lt", "luxembourg": "lu", "macao": "mo",
    "macau": "mo", "macedonia": "mk", "north macedonia": "mk", "malaysia": "my",
    "mali": "ml", "malta": "mt", "mexico": "mx", "moldova": "md",
    "mongolia": "mn", "montenegro": "me", "morocco": "ma", "netherlands": "nl",
    "new zealand": "nz", "nicaragua": "ni", "nigeria": "ng", "northern ireland": "gb-nir",
    "norway": "no", "oman": "om", "pakistan": "pk", "palestine": "ps",
    "panama": "pa", "paraguay": "py", "peru": "pe", "philippines": "ph",
    "poland": "pl", "portugal": "pt", "qatar": "qa", "romania": "ro",
    "russia": "ru", "saudi arabia": "sa", "scotland": "gb-sct", "senegal": "sn",
    "serbia": "rs", "singapore": "sg", "slovakia": "sk", "slovenia": "si",
    "south africa": "za", "south korea": "kr", "korea, south": "kr", "spain": "es",
    "sweden": "se", "switzerland": "ch", "syria": "sy", "taiwan": "tw",
    "tajikistan": "tj", "tanzania": "tz", "thailand": "th", "tunisia": "tn",
    "turkey": "tr", "türkiye": "tr", "turkmenistan": "tm", "uganda": "ug",
    "ukraine": "ua", "united arab emirates": "ae", "uae": "ae", "united states": "us",
    "usa": "us", "uruguay": "uy", "uzbekistan": "uz", "venezuela": "ve",
    "vietnam": "vn", "wales": "gb-wls", "yemen": "ye", "zambia": "zm",
    "zimbabwe": "zw", "burkina faso": "bf", "guinea": "gn", "sierra leone": "sl",
    "gambia": "gm", "togo": "tg", "benin": "bj", "liberia": "lr",
    "cape verde": "cv", "cabo verde": "cv", "mauritania": "mr", "niger": "ne",
    "chad": "td", "sudan": "sd", "south sudan": "ss", "eritrea": "er",
    "djibouti": "dj", "somalia": "so", "madagascar": "mg", "mauritius": "mu",
    "seychelles": "sc", "comoros": "km", "burundi": "bi", "rwanda": "rw",
    "congo": "cg", "dr congo": "cd", "congo, democratic republic": "cd",
    "equatorial guinea": "gq", "guinea-bissau": "gw",
}


def _country_to_flag(country_name: str) -> str:
    """Map a country name to flagcdn.com URL (e.g. 'Czech Republic' → cz.png).

    Mirrors phase2_generic.country_to_flag. Returns empty string if unknown.
    """
    if not country_name:
        return ""
    key = str(country_name).strip().lower()
    code = _COUNTRY_CODES.get(key)
    if code:
        return f"https://flagcdn.com/w20/{code}.png"
    return ""


# --- Strip trailing reason keywords from player names ---
# Mirrors phase2_generic._strip_missing_reason_suffix (Jul 23 2026 spec).
# The Flashscore API sometimes appends a reason keyword to player.name for
# missing players (e.g. "Vindahl Peter Foot Injury" instead of "Vindahl Peter").
# The reason is preserved separately in last3_missing[].reason. This helper
# returns the cleaned name; the reason is rendered only in the missing-cell
# hover tooltip, NEVER in the Player column.
#
# Jul 23 2026 — see skill formalert-team-page-template / `_strip_missing_reason_suffix`
# for the full algorithm + the long list of token examples.
# KEEP THIS LIST IN SYNC WITH phase2_generic._REASON_TOKENS.
_REASON_TOKENS = (
    # Multi-word injury types (Flashscore API uses these verbatim)
    "Achilles Tendon Injury", "Hamstring Injury", "Knee Injury",
    "Muscle Injury", "Lower Back Injury", "Head Injury", "Groin Injury",
    "Ankle Injury", "Thigh Injury", "Toe Injury", "Foot Injury",
    "Calf Injury", "Shoulder Injury", "Hip Injury", "Neck Injury",
    "Wrist Injury", "Hand Injury", "Finger Injury",
    "Cruciate Ligament", "Cruciate Ligament Injury", "Medial Collateral Ligament",
    "Broken Leg", "Broken Foot", "Broken Ankle", "Broken Arm", "Broken Nose",
    "Broken Hand", "Broken Finger", "Fractured Rib",
    "Concussion", "ACL Injury", "MCL Injury", "PCL Injury",
    "Torn Muscle", "Torn Ligament", "Torn Meniscus", "Torn Hamstring",
    "Stomach Flu", "Viral Infection", "Bacterial Infection",
    "Heart Problems", "Health problems",
    # Single-word body parts / surgery / status (NEW Jul 23 2026 — fixes
    # "Joelinton Thigh", "Dos Santos Matthew Calf", "Bruninho Muscle")
    "Muscle", "Thigh", "Calf", "Shoulder", "Groin", "Knee", "Hamstring",
    "Achilles", "Achilles Tendon", "Ankle", "Foot", "Hip", "Neck",
    "Wrist", "Hand", "Finger", "Back", "Rib", "Toe", "Elbow", "Leg", "Arm",
    "Injury", "Illness", "Surgery", "Operation", "Rest",
    "Yellow Cards", "Yellow Card", "Red Card",
    "Suspended", "Suspension", "Banned",
    "Personal Reasons", "Private Reasons", "Family Reasons",
    "Transfer negotiations", "Transfer Negotiations", "Transfer Negotiation",
    "Loan agreement", "International duty",
    "Not in squad", "Not in match squad", "Coach's decision",
    "Inactive", "Resting", "Disciplinary",
    "Lacking Match Fitness", "Rest",
)

# Date pattern (matches trailing " 01.08.2026" etc.) — Jul 23 2026.
_DATE_PATTERN_RE = None  # lazy-compiled
def _date_pattern():
    global _DATE_PATTERN_RE
    if _DATE_PATTERN_RE is None:
        import re as _re
        _DATE_PATTERN_RE = _re.compile(
            r'\s+\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\s*$'
        )
    return _DATE_PATTERN_RE


def _strip_missing_reason_suffix(name):
    """Strip a trailing reason keyword (and optional date) from a player name.

    Examples (from real Jul 2026 cache data):
        "Estêvão Hamstring Injury 01.08.2026"       → "Estêvão"
        "Gittens Jamie Hamstring Injury 01.08.2026"  → "Gittens Jamie"
        "Wesley Franca Muscle Injury 02.08.2026"     → "Wesley Franca"
        "Joelinton Thigh"                             → "Joelinton"
        "Miley Lewis Broken Leg 02.09.2026"           → "Miley Lewis"
        "Hollerbach Benedict Achilles Tendon Injury 02.08.2026"
                                                       → "Hollerbach Benedict"
        "Agyekum Lawrence Shoulder"                   → "Agyekum Lawrence"
        "Vindahl Peter Foot Injury"                   → "Vindahl Peter"
        "Estêvão"                                     → "Estêvão"  (no reason)
        "Neymar"                                      → "Neymar"    (no reason)

    Algorithm:
      1. Strip any trailing date first (e.g. " 01.08.2026").
      2. While the last 1-4 tokens match a known reason token, strip them.
      3. If we strip everything (e.g. name = "Thigh"), restore the original.
      4. Otherwise return the cleaned name (1+ tokens).
    """
    if not name:
        return name
    original = str(name)
    # 1. Strip trailing date
    name = _date_pattern().sub('', original).strip()
    parts = name.split()
    if not parts:
        return original  # safety: don't return empty
    # 2. Strip trailing reason tokens (try longest first)
    for _ in range(4):  # max 4 reason words
        if not parts:
            break
        matched = False
        for reason in sorted(_REASON_TOKENS, key=len, reverse=True):
            r_parts = reason.split()
            if len(parts) >= len(r_parts) and parts[-len(r_parts):] == r_parts:
                parts = parts[:-len(r_parts)]
                matched = True
                break
        if not matched:
            break
    # 3. If we stripped everything, restore original
    if not parts:
        return original
    return " ".join(parts)


# Position mapping (Skill formalert-team-page-template) — section name → 2-letter code.
# Verified across all major leagues Jul 2026: every top-flight team maps cleanly.
_POS_MAP = {
    "goalkeepers": "GK", "goalkeeper": "GK",
    "defenders": "DF", "defender": "DF",
    "midfielders": "MF", "midfielder": "MF",
    "forwards": "FW", "forward": "FW", "striker": "FW", "strikers": "FW",
    "winger": "FW", "wingers": "FW", "attacker": "FW", "attackers": "FW",
}


def _map_position(section_name: str) -> str:
    """Map a section name (e.g. 'Goalkeepers') to 2-letter code (GK/DF/MF/FW).

    Falls back to first 2 letters uppercased for unknown section names
    (should never happen in well-formed Flashscore responses).
    """
    if not section_name:
        return ""
    key = str(section_name).strip().lower()
    if key in _POS_MAP:
        return _POS_MAP[key]
    # Defensive fallback — e.g. "Centre-Backs" → "CE"
    return key[:2].upper()


def refresh_player_details(player, delay=0.25, force=False, is_national=False):
    """Fetch /players/details and update market_value, image_path, etc.

    Jul 28 2026: also capture current club + club logo from
    /players/details, but ONLY for national-team players. For club-
    team players, d.team is their own club (Manchester City for a
    Manchester City player) which we do NOT want to render in the
    Nat column — that's where the player's nationality flag belongs.
    """
    # Delta refresh (Jul 23 2026): skip per-player API call if section is fresh.
    # force=True no longer bypasses this check — see refresh_squad comment.
    tid = player.get('_team_id', '')
    if tid and _section_is_fresh(tid, 'player_details', PLAYER_DETAILS_TTL_SECONDS):
        return  # market_value/age already in cache
    purl = player.get("player_url", "")
    if not purl:
        return
    # purl is like "/player/qirko-pano/vBb94SxF/"
    full_url = f"https://{HOST}/api/flashscore/v2/players/details?player_url={urllib.parse.quote(purl, safe='/?=')}"
    d = _fetch(full_url)
    if not d or not isinstance(d, dict):
        return
    # market_value: keep real value, "" when missing (no "None" / "–")
    mv = d.get("market_value")
    if mv not in (None, "", 0, "0", "–", "—", "?", "N/A"):
        player["market_value"] = mv
    elif "market_value" in player and player["market_value"] in (None, "", 0):
        # Don't overwrite a real age/club value with empty; only clear if also empty.
        # Use _clean_cell for consistency with the rest of the pipeline.
        player["market_value"] = _clean_cell(mv)
    img = d.get("image_path")
    if img:
        player["image_path"] = img
    stats = d.get("statistics") or d.get("stats") or {}
    if isinstance(stats, dict):
        for k in ["goals", "assists", "yellow_cards", "red_cards", "matches_played", "minutes_played"]:
            if k in stats:
                player[k] = stats[k]
    # Jul 28 2026: capture player's CURRENT CLUB from /players/details
    # for national-team display ONLY (e.g. Austria > "Werder Bremen"
    # with badge). For club-team players we deliberately skip this:
    # d.team is their own club (Manchester City for a Manchester City
    # player), which would collide with the flag-rendering logic in
    # lineup_team_view.get_nat_html step 1 (club-logo branch).
    if is_national:
        team_info = d.get("team") or {}
        if isinstance(team_info, dict):
            club_name = team_info.get("name") or ""
            club_logo = team_info.get("image_path") or ""
            if club_name:
                player["club"] = club_name
            if club_logo:
                player["club_logo"] = club_logo
    time.sleep(delay)


def refresh_team_details(team_id, slug, force=False):
    """Fetch /teams/details and return {image_path, stadium, city, capacity, name}.

    Real API response (verified Jul 22 2026):
        {
            "team_id": "6qA358jH",
            "name": "Sparta Prague",
            "image_path": "https://static.flashscore.com/res/image/data/lIHy1EfM-lWOFh0RD.png",
            "stadium": "epet ARENA",
            "city": "Prague",
            "capacity": 18349
        }

    This is the ONLY place the team logo (image_path) comes from. The
    /teams/squad endpoint does NOT return image_path. Without this call,
    the cache file would have team.image_path = None and the UI would
    fall back to a letter placeholder.
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/details?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    d = _fetch(url)
    if not d or not isinstance(d, dict):
        return {}
    return {
        "image_path": d.get("image_path") or "",
        "stadium": d.get("stadium") or "",
        "city": d.get("city") or "",
        "capacity": d.get("capacity") or 0,
        "name": d.get("name") or "",
    }


def refresh_fixtures(team_id, force=False):
    """Fetch /teams/fixtures and return list of next 5 upcoming matches.

    Real API shape (same envelope as /teams/results):
        [
            {tournament_id, full_name, name, matches: [{match_id, timestamp, ...}]}
        ]
    Jul 30 2026 v13: sort DESC + filter future-only before slicing.
    Returns matches sorted DESC by timestamp, top 5 future.
    """
    # Delta refresh (Jul 23 2026): skip API call if fixtures are fresh.
    # force=True no longer bypasses this check — see refresh_squad comment.
    if _section_is_fresh(team_id, 'fixtures', FIXTURES_TTL_SECONDS):
        cache = _read_cache(team_id)
        cached = (cache or {}).get('fixtures', [])
        if cached:
            print(f'[delta] fixtures fresh, reusing {len(cached)} cached fixtures (0 API calls)')
            return list(cached)
    url = f"https://{HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
    data = _fetch(url)
    if not data:
        return []
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(rows, list) or not rows:
        return []
    flat = []
    for env in rows:
        if not isinstance(env, dict):
            continue
        tname = env.get("full_name") or env.get("name") or ""
        tshort = _short_tournament(env.get("name") or "")
        for m in env.get("matches", []) or []:
            if not isinstance(m, dict):
                continue
            flat.append((m, tname, tshort))
    # v13: filter future-only, then sort ASC, take top 5 nearest.
    # API /teams/fixtures returns past + future matches mixed.
    # We want the 5 NEAREST upcoming matches.
    import time as _t
    _now_ts = int(_t.time())
    flat = [x for x in flat if int(x[0].get("timestamp") or 0) >= _now_ts]
    flat.sort(key=lambda x: int(x[0].get("timestamp") or 0))  # ASC = nearest first
    flat = flat[:5]
    out = []
    for m, tname, tshort in flat:
        mid = m.get("match_id") or m.get("id")
        home = m.get("home_team") or m.get("home") or {}
        away = m.get("away_team") or m.get("away") or {}

        def _team_info(t):
            if isinstance(t, dict):
                return {
                    "id": t.get("team_id") or t.get("id"),
                    "name": t.get("name") or t.get("short_name") or t.get("full_name") or "",
                }
            return {"id": None, "name": str(t) if t else ""}

        home_info = _team_info(home)
        away_info = _team_info(away)
        ts = m.get("timestamp") or m.get("start_timestamp") or 0
        date_str, time_str = "", ""
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts))
                date_str = dt.strftime("%d/%m")
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass
        side = "home" if str(home_info.get("id") or "") == str(team_id) else "away"
        out.append({
            "match_id": mid,
            "date": date_str,
            "time": time_str,
            "timestamp": int(ts) if ts else 0,
            "tournament_name_short": tshort,
            "tournament_name_full": tname,
            "home_team": home_info["name"] or "",
            "home_team_id": home_info["id"] or "",
            "away_team": away_info["name"] or "",
            "away_team_id": away_info["id"] or "",
            "side": side,
        })
    return out


def refresh_results(team_id, force=False):
    """Fetch /teams/results and return list of last 3 matches (with lineups).

    Jul 22 2026 — Senior Python Flask refactor:
    Real Flashscore API response shape (verified):
        [
            {
                "tournament_id": "U3iTWJUr",
                "tournament_url": "/football/world/club-friendly/",
                "full_name": "WORLD: Club Friendly",
                "name": "Club Friendly",
                "matches": [
                    {"match_id": "MgtcCHgC", "timestamp": 1784282400,
                     "home_team": {"team_id": "...", "name": "..."},
                     "away_team": {...},
                     "scores": {"home": 2, "away": 0}}
                ]
            },
            ...
        ]

    The previous code iterated `data[:3]` treating each tournament as a
    match — which is why match_id was always None and last3 was always empty.
    Now we flatten ALL matches across all tournaments, sort by timestamp DESC,
    and take the top 3 most recent.
    """
    # Delta refresh (Jul 23 2026): skip API call if results are fresh.
    # force=True no longer bypasses this check — see refresh_squad comment.
    if _section_is_fresh(team_id, 'results', RESULTS_TTL_SECONDS):
        cache = _read_cache(team_id)
        cached_matches = (cache or {}).get('matches', [])
        if cached_matches:
            print(f'[delta] results fresh, reusing {len(cached_matches)} cached matches (0 API calls)')
            return list(cached_matches)
    url = f"https://{HOST}/api/flashscore/v2/teams/results?team_id={team_id}&page=1"
    data = _fetch(url)
    if not data:
        return []
    # Normalize to list of tournament envelopes
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(rows, list) or not rows:
        return []

    # Flatten: extract every match from every tournament envelope
    flat = []
    for env in rows:
        if not isinstance(env, dict):
            continue
        tname = env.get("full_name") or env.get("name") or ""
        tshort = env.get("name") or ""
        tshort = _short_tournament(tshort)  # normalize via Skill map
        for m in env.get("matches", []) or []:
            if not isinstance(m, dict):
                continue
            flat.append((m, tname, tshort))
    # Sort by timestamp DESC, take top 3
    flat.sort(key=lambda x: int(x[0].get("timestamp") or 0), reverse=True)
    flat = flat[:3]

    matches = []
    for m, tname, tshort in flat:
        mid = m.get("match_id") or m.get("id") or m.get("MatchId")
        home = m.get("home_team") or m.get("home") or {}
        away = m.get("away_team") or m.get("away") or {}

        def _team_info(t):
            if isinstance(t, dict):
                return {
                    "id": t.get("team_id") or t.get("id"),
                    "name": t.get("name") or t.get("short_name") or t.get("full_name") or "",
                }
            return {"id": None, "name": str(t) if t else ""}

        home_info = _team_info(home)
        away_info = _team_info(away)
        # Score: API returns `m["scores"] = {"home": int, "away": int}` (verified).
        score = ""
        scores = m.get("scores")
        if isinstance(scores, dict):
            h, a = scores.get("home"), scores.get("away")
            if h is not None and a is not None:
                score = f"{h}-{a}"
        if not score:
            score = m.get("score") or m.get("ft_score") or ""
        if not score and isinstance(m.get("home_score"), int):
            score = f"{m.get('home_score')}-{m.get('away_score')}"

        # Timestamp
        ts = m.get("timestamp") or m.get("start_timestamp") or 0
        date_str = ""
        time_str = ""
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts))
                date_str = dt.strftime("%d/%m")
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass

        # Side (home/away relative to our team) — drives cell color in UI
        side = "home" if str(home_info.get("id") or "") == str(team_id) else "away"

        matches.append({
            "match_id": mid,
            "date": date_str,
            "time": time_str,
            "timestamp": int(ts) if ts else 0,
            "tournament_name_short": tshort,
            "tournament_name_full": tname,
            "home_team": home_info["name"] or "",
            "home_team_id": home_info["id"] or "",
            "away_team": away_info["name"] or "",
            "away_team_id": away_info["id"] or "",
            "score": score,
            "side": side,
        })
    return matches


# Skill formalert-team-page-template TOURNAMENT_SHORT map (mirrors phase2_generic)
_TOURNAMENT_SHORT_MAP = {
    "abissnet superiore": "SL", "kategoria e parë": "1D", "kategoria superiore": "1D",
    "ligue 1": "L1", "ligue 2": "L2", "primera divisió": "PD",
    "liga profesional": "LPF", "copa de la liga profesional": "LPF",
    "conmebol libertadores": "UCL", "conmebol sudamericana": "UEL",
    "conmebol recopa": "SC", "copa argentina": "CUP",
    "trofeo de campeones": "SC",
    "albanian cup": "CUP", "algeria cup": "CUP", "andorra cup": "CUP",
    "argentina cup": "CUP", "austrian cup": "CUP", "austrian bundesliga": "BL",
    "belgian cup": "CUP", "belgian pro league": "JL",
    "bolivian cup": "CUP", "bosnian cup": "CUP",
    "brazilian cup": "CUP", "brazilian serie a": "SA", "brazilian serie b": "SB",
    "bulgarian cup": "CUP",
    "chile: liga de primera": "LP", "chile: super cup": "SC",
    "bolivia: division profesional": "DP",
    "bolivia: copa de la division profesional": "CUP",
    "bolivia: copa pacena": "CUP", "bolivia: copa simon bolivar": "CUP",
    "bosnia: wwin liga bih": "BH", "bosnia: kup bih": "CUP",
    "brazil: serie a betano": "SA", "brazil: serie a": "SA",
    "brazil: copa do brasil": "CUP",
    "bulgaria: efbet league": "EL", "bulgaria: bulgarian first league": "EL",
    "bulgaria: kupa na balgariya": "CUP",
    "china: super league": "SL", "china: chinese super league": "SL",
    "china: fa cup": "CUP", "china: chinese fa cup": "CUP",
    "colombia: primera a": "PA", "colombia: primera a - apertura": "PA",
    "colombia: primera a - play offs": "PA", "colombia: copa colombia": "CUP",
    "colombia: copa libertadores": "UCL",
    "croatia: hnl": "HN", "croatia: prva nl": "2L", "croatia: druga nl": "3L",
    "croatia: croatian cup": "CUP",
    "cyprus: cyprus league": "CPL",
    "cyprus: cyprus league - championship group": "CPL",
    "cyprus: cyprus league - relegation group": "CPL",
    "cyprus: cypriot cup": "CUP",
    "czech: chance liga": "CZ", "czech: czech first league": "CZ",
    "czech: mol cup": "CUP",
    "uefa champions league": "UCL", "uefa europa league": "UEL",
    "uefa conference league": "ECL",
    "euro: champions league": "UCL", "euro: europa league": "UEL",
    "euro: conference league": "ECL",
    "euro: champions league - qualification": "UCLQ",
    "euro: europa league - qualification": "UELQ",
    "euro: conference league - qualification": "ECLQ",
    "world cup": "WC", "euro": "EURO", "league cup": "LC", "fa cup": "FA",
    "club friendly": "FR", "world: club friendly": "FR",
    "super cup": "SC", "copa del rey": "CR",
    "dfb-pokal": "CUP", "coppa italia": "CUP",
    "eredivisie": "ER", "primeira liga": "PL",
    "super league": "SL", "super lig": "SL",
}


def _short_tournament(name: str) -> str:
    """Look up TOURNAMENT_SHORT (mirrors phase2_generic TOURNAMENT_SHORT).

    Falls back to first 3 letters uppercased.
    """
    if not name:
        return ""
    key = str(name).strip().lower()
    if key in _TOURNAMENT_SHORT_MAP:
        return _TOURNAMENT_SHORT_MAP[key]
    # Try with prefix stripped (e.g. "WORLD: Club Friendly" → "club friendly")
    if ":" in key:
        tail = key.split(":", 1)[1].strip()
        if tail in _TOURNAMENT_SHORT_MAP:
            return _TOURNAMENT_SHORT_MAP[tail]
    # Generic fallback
    return key[:3].upper() if len(key) >= 3 else key.upper()


def refresh_lineups_for_matches(matches, team_id):
    """For each match, fetch /lineups and attach to match dict.

    Returns a dict {(match_index, player_id): {status, missing_info}} so
    refresh_team() can attach `last3` and `last3_missing` to each player.

    Real API shape (verified Jul 22 2026):
        [
            {"side": "home", "startingLineups": [11 items], "substitutes": [6],
             "missingPlayers": [...], "formation": "3-4-3"},
            {"side": "away", "startingLineups": [11 items], "substitutes": [6],
             "missingPlayers": [...], "formation": "4-3-3"},
        ]

    The previous code looked for `team_id` per envelope — WRONG, the envelope
    uses `side` ("home"/"away"). We match by `side` against the home_team_id
    stored in our match dict.

    Schema per match (after processing):
        m["lineup_player_ids"]    — list of player_id (START + SUB) for OUR team
        m["lineup_starting_ids"]  — list of player_id (START only) for OUR team
    """
    out = {}
    for mi, m in enumerate(matches):
        mid = m.get("match_id")
        if not mid:
            continue
        our_side = m.get("side")  # "home" or "away" — set by refresh_results
        if not our_side:
            continue
        url = f"https://{HOST}/api/flashscore/v2/matches/match/lineups?match_id={mid}"
        d = _fetch(url)
        if not d or not isinstance(d, list):
            time.sleep(0.2)
            continue
        starting_ids = []
        sub_ids = []
        missing = []
        captain_ids = []
        for lu in d:
            if not isinstance(lu, dict):
                continue
            if lu.get("side") != our_side:
                continue
            starting = lu.get("startingLineups") or lu.get("starting") or []
            subs = lu.get("substitutes") or lu.get("substitutesLineups") or []
            missing = lu.get("missingPlayers") or lu.get("missing") or []
            if isinstance(starting, list):
                starting_ids = [str(p.get("player_id") or p.get("id"))
                                for p in starting if (p.get("player_id") or p.get("id"))]
                captain_ids = [str(p.get("player_id") or p.get("id"))
                               for p in starting
                               if (p.get("player_id") or p.get("id")) and p.get("is_captain")]
            if isinstance(subs, list):
                sub_ids = [str(p.get("player_id") or p.get("id"))
                           for p in subs if (p.get("player_id") or p.get("id"))]
            break  # found our envelope
        m["lineup_starting_ids"] = starting_ids
        m["lineup_player_ids"] = starting_ids + sub_ids
        m["lineup_captain_ids"] = captain_ids
        for pid in starting_ids:
            out[(mi, pid)] = {"status": "START", "is_captain": pid in captain_ids}
        for pid in sub_ids:
            if (mi, pid) not in out:
                out[(mi, pid)] = {"status": "SUB", "is_captain": False}
        if isinstance(missing, list):
            for mp in missing:
                if not isinstance(mp, dict):
                    continue
                pid = str(mp.get("player_id") or mp.get("id") or "")
                reason = mp.get("reason") or ""
                if not pid:
                    continue
                emoji, color = _missing_emoji(reason)
                out[(mi, pid)] = {
                    "status": "",
                    "missing_info": {
                        "emoji": emoji,
                        "reason": reason,
                        "color": color,
                        "side": our_side,
                    }
                }
        time.sleep(0.2)
    return out


# --- Missing-player emoji map (mirrors phase2_generic._missing_emoji) ---
def _missing_emoji(reason: str) -> tuple:
    """Map API reason text to (emoji, color). Mirrors phase2_generic._missing_emoji.

    Per Skill formalert-team-page-template:
    - ❌ (red) for injuries / illness
    - 🟥 for Red card
    - 🟨 for Yellow cards
    - 📄 for Loan
    - 🛫 for International duty
    - ⛔️ (gray) for Inactive / Coach's decision / Suspended
    """
    if not reason:
        return ("", "")
    r = str(reason).strip().lower()
    # Injuries / health
    injury_kw = [
        "achilles tendon injury", "lower back injury", "hamstring injury",
        "knee injury", "muscle injury", "shoulder injury", "ankle injury",
        "back injury", "arm injury", "calf injury", "elbow injury", "leg injury",
        "groin injury", "head injury", "thigh injury", "toe injury", "foot injury",
        "broken leg", "broken calfbone", "broken jawbone",
        "injury", "illness", "health problems", "heart problems",
    ]
    if any(k in r for k in injury_kw):
        return ("❌", "#dc3545")
    if "red card" in r:
        return ("🟥", "#dc3545")
    if "yellow card" in r:
        return ("🟨", "#d4a017")
    if "loan" in r:
        return ("📄", "#6c757d")
    if "international" in r or "duty" in r:
        return ("🛫", "#0d6efd")
    if any(k in r for k in ("inactive", "coach's decision", "suspended", "rest")):
        return ("⛔️", "#6c757d")
    # Default — gray missing indicator
    return ("⛔️", "#6c757d")


def refresh_team(team_id, force=False):
    """Sync refresh: fetch squad + last 3 + lineups + player_details from Flashscore API.
    Returns True if cache was updated, False otherwise (already fresh, in-progress, or error).

    Jul 22 2026 — Senior Python Flask refactor:
    - Squad taken from "Total" group (refresh_squad fix above)
    - Position mapped to 2-letter code (GK/DF/MF/FW)
    - last3 + last3_missing attached to each player (parity with phase2_generic)
    - Coach section skipped in squad
    - team.image_path populated from /teams/details (logo)
    - stadium/city/capacity populated from /teams/details
    - fixtures[] populated from /teams/fixtures
    """
    if team_id in _refresh_in_progress:
        return False
    if not force and is_fresh(team_id):
        return False
    info = _get_team_info(team_id)
    if not info:
        return False
    country, champ, slug = info
    _refresh_in_progress.add(team_id)
    try:
        # 0. Team details (logo, stadium, city, capacity)
        #    MUST be called before building the team dict so image_path is set.
        details = refresh_team_details(team_id, slug)
        _mark_section_updated(team_id, "team_details")
        # 1. Squad (from Total group, with position mapping)
        _last_squad_coach["data"] = None  # Jul 25 2026: reset before call
        players = refresh_squad(team_id, slug, info, force=force)
        if players is None:
            return False
        # 1a. Mark squad as fresh and pass _team_id to each player so
        #     refresh_player_details can also skip when fresh.
        for p in players:
            p["_team_id"] = team_id
        _mark_section_updated(team_id, "squad")
        # 2. Last 3 matches
        matches = refresh_results(team_id, force=force)
        _mark_section_updated(team_id, "results")
        # 3. Lineups for matches — also returns per-(match, player) status + missing
        lineup_index = refresh_lineups_for_matches(matches, team_id)
        # 4. Attach last3 + last3_missing to each player (parity with phase2_generic.py)
        for p in players:
            pid = p.get("player_id", "")
            l3 = ["", "", ""]
            l3m = [None, None, None]
            l3c = [False, False, False]
            for i in range(min(3, len(matches))):
                entry = lineup_index.get((i, pid))
                if not entry:
                    continue
                l3[i] = entry.get("status", "")
                if l3[i] == "START" and entry.get("is_captain"):
                    l3c[i] = True
                mi = entry.get("missing_info")
                if mi:
                    l3m[i] = mi
            p["last3"] = l3
            p["last3_missing"] = l3m
            p["last3_captain"] = l3c
        # 5. Player details (market_value, image) - parallel
        if players:
            # Jul 23 2026: pass force=force so ♻️ Refresh bypasses the 4h
            # player_details TTL. Without this, ex.map defaulted to
            # force=False and skipped every player when section was fresh,
            # leaving the cache with empty MV values.
            # Jul 28 2026: pass is_national so club-team players don't get
            # their own club written into player["club"] (which would
            # route them through the club-logo branch instead of the
            # nationality flag branch in get_nat_html).
            championship = info[1] if isinstance(info, tuple) else ""
            is_national = championship == "National Teams"
            with ThreadPoolExecutor(max_workers=2) as ex:
                list(ex.map(lambda p: refresh_player_details(p, force=force, is_national=is_national), players))
            _mark_section_updated(team_id, "player_details")
        # 6. Fixtures (next 5 upcoming) — populates fixtures[] in cache
        fixtures = refresh_fixtures(team_id, force=force)
        _mark_section_updated(team_id, "fixtures")
        # 7. Build cache — preserve existing keys (coach etc.), overlay new data
        cache = _read_cache(team_id)
        # Prefer API name if available, else leagues_data.json, else existing
        team_name = (
            details.get("name")
            or cache.get("team", {}).get("name", "")
            or ""
        )
        cache["team"] = {
            "id": team_id,
            "name": team_name,
            "country": country,
            "championship": champ,
            "slug": slug,
            "image_path": details.get("image_path", "") or cache.get("team", {}).get("image_path", ""),
        }
        # Stadium / city / capacity (overlays existing values if API returned them)
        if details.get("stadium"):
            cache["stadium"] = details["stadium"]
        if details.get("city"):
            cache["city"] = details["city"]
        if details.get("capacity"):
            cache["capacity"] = details["capacity"]
        # Jul 25 2026: coach from /teams/squad (side-channel _last_squad_coach
        # set by refresh_squad). API returns coach in a separate group
        # "Coach" with one player entry. Only overwrite if API returned a
        # real name — never clobber existing coach with empty.
        if _last_squad_coach.get("data") and _last_squad_coach["data"].get("name"):
            cache["coach"] = _last_squad_coach["data"]
        cache["players"] = players
        cache["matches"] = matches
        cache["fixtures"] = fixtures
        # Jul 30 2026: Fixture Overview metric (calendar density, was Fixture Congestion).
        # Compute from the next 5 upcoming fixtures stored above.
        try:
            from fixture_congestion import compute_fixture_congestion
            cache["fixture_congestion"] = compute_fixture_congestion(fixtures)
        except Exception as _fc_err:
            cache["fixture_congestion"] = None
            print("[fo] could not compute Fixture Overview: " + str(_fc_err))
        cache["last_updated"] = datetime.now().isoformat()
        _write_cache(team_id, cache)
        return True
    finally:
        _refresh_in_progress.discard(team_id)


def ensure_fresh_async(team_id):
    """Trigger background refresh if cache is stale. Safe to call from request handler."""
    if team_id in _refresh_in_progress:
        return
    if is_fresh(team_id):
        return
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(asyncio.to_thread(refresh_team, team_id))
    except RuntimeError:
        # No event loop - spawn thread
        import threading
        t = threading.Thread(target=refresh_team, args=(team_id,), daemon=True)
        t.start()


# ---------------------------------------------------------------------------
# H2H + Last Matches (Match mode popup)
# Jul 22 2026 — Senior Python Flask refactor.
# Three Flashscore endpoints:
#   GET /matches/h2h?match_id={id}
#   GET /teams/results?team_id={id}&page=1
# Plus the /teams/details for stadium/referee.
# Called ONLY on click of the ‼️ button in Match mode — never at page load.
# ---------------------------------------------------------------------------
def _fetch_json(url):
    """Helper: GET a JSON URL with our RapidAPI headers (skip SSL verify)."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=HEADERS)
        body = urllib.request.urlopen(req, context=ctx, timeout=20).read()
        return json.loads(body)
    except Exception as e:
        return {"_error": str(e)}


def _parse_match_row(m, my_team_id):
    """Convert a Flashscore match envelope into a UI-ready dict.

    Real API shape (verified):
        m = {
            "match_id": "MgtcCHgC",
            "timestamp": 1784282400,
            "home_team": {"team_id": "2wZ...", "name": "Home"},
            "away_team": {"team_id": "6qA...", "name": "Away"},
            "scores": {"home": 2, "away": 1}
        }

    Args:
        m: the raw match dict
        my_team_id: which side is "ours" (sets my_side='home'/'away')
    """
    if not isinstance(m, dict):
        return None
    mid = m.get("match_id") or m.get("id")
    home = m.get("home_team") or m.get("home") or {}
    away = m.get("away_team") or m.get("away") or {}
    if isinstance(home, str):
        home = {"name": home}
    if isinstance(away, str):
        away = {"name": away}
    home_id = (home.get("team_id") or home.get("id")) if isinstance(home, dict) else None
    away_id = (away.get("team_id") or away.get("id")) if isinstance(away, dict) else None
    home_name = (home.get("name") or home.get("short_name") or home.get("full_name") or "") if isinstance(home, dict) else str(home or "")
    away_name = (away.get("name") or away.get("short_name") or away.get("full_name") or "") if isinstance(away, dict) else str(away or "")
    # Score: API returns nested `scores` object (verified Jul 22 2026)
    hs, aws = None, None
    scores = m.get("scores")
    if isinstance(scores, dict):
        if scores.get("home") is not None:
            hs = scores.get("home")
        if scores.get("away") is not None:
            aws = scores.get("away")
    if hs is None or aws is None:
        score_str = m.get("score") or ""
        if "-" in str(score_str):
            try:
                ph, pa = str(score_str).split("-", 1)
                if hs is None:
                    hs = int(ph.strip())
                if aws is None:
                    aws = int(pa.strip())
            except (ValueError, TypeError):
                pass
    ts = m.get("timestamp") or m.get("start_timestamp") or 0
    date_str = ""
    if ts:
        try:
            dt = datetime.fromtimestamp(int(ts))
            date_str = dt.strftime("%d.%m.%y")
        except (ValueError, TypeError, OSError):
            pass
    my_side = None
    if my_team_id:
        if str(home_id or "") == str(my_team_id):
            my_side = "home"
        elif str(away_id or "") == str(my_team_id):
            my_side = "away"
    return {
        "match_id": mid,
        "date": date_str,
        "timestamp": int(ts) if ts else 0,
        "home": {"id": home_id, "name": home_name},
        "away": {"id": away_id, "name": away_name},
        "score_home": hs,
        "score_away": aws,
        "tournament": m.get("tournament_short") or m.get("tournament") or "",
        "my_side": my_side,
    }


def fetch_h2h(match_id, max_results=5, my_team_id="", opp_team_id=""):
    """Return the last N true head-to-head matches between my_team and opp_team.

    Jul 22 2026 — the Flashscore /matches/h2h endpoint does NOT return
    head-to-head games between two specific teams; it returns the full
    match list of whatever tournament the match_id belongs to. So we
    compute real H2H by intersecting the /teams/results of both teams
    and keeping only matches where the two specific teams played each
    other (i.e. the match involves BOTH my_team_id and opp_team_id).

    Implementation notes:
      - Each /teams/results page holds ~40-45 most recent matches
        (~1 year for active clubs). For teams that play each other
        infrequently the mutual games can be on later pages. We walk
        up to MAX_H2H_PAGES pages per side until we have enough mutual
        matches or run out of history.
      - The intersection by match_id is sufficient for correctness:
        a match_id is globally unique and only appears in a team's
        /teams/results if that team played in it. So if match_id is
        in BOTH lists, both teams played in it -- which is exactly
        a head-to-head meeting.
      - We also try the Flashscore "head-to-head" endpoint variant
        (team_id=X&team_id=Y) as a secondary source, and merge any
        results we find there that are not already in the
        intersection. This endpoint is unreliable (returns the full
        tournament schedule for the last team_id) but is cheap to try.

    Args:
        match_id: the current match_id (hint only; not used to drive the API)
        max_results: cap on the returned list (default 5)
        my_team_id, opp_team_id: the two team_ids whose mutual history
            we want to display

    Returns:
        list of dicts (see _parse_match_row) -- newest first, capped at
        max_results. Only matches that involved BOTH teams are included.
    """
    MAX_H2H_PAGES = 10  # ~10*40 = 400 results per side ≈ 5-8 years of history
    if not my_team_id or not opp_team_id:
        return []
    # Page 1 first -- fast path for teams that have very recent H2H.
    my_results = fetch_team_results(my_team_id, my_team_id=my_team_id, max_results=200, max_pages=1)
    opp_results = fetch_team_results(opp_team_id, my_team_id=opp_team_id, max_results=200, max_pages=1)
    opp_match_ids = {m.get("match_id") for m in opp_results if m.get("match_id")}
    h2h = [m for m in my_results if m.get("match_id") in opp_match_ids]
    if len(h2h) >= max_results:
        return h2h[:max_results]
    # Walk additional pages until we have enough mutual matches or run out.
    for page in range(2, MAX_H2H_PAGES + 1):
        my_more = fetch_team_results(my_team_id, my_team_id=my_team_id, max_results=200, max_pages=page)
        opp_more = fetch_team_results(opp_team_id, my_team_id=opp_team_id, max_results=200, max_pages=page)
        # Refresh opp set with the larger window.
        opp_match_ids = {m.get("match_id") for m in opp_more if m.get("match_id")}
        # Add any newly-found mutual matches (in DESC order).
        existing_ids = {m.get("match_id") for m in h2h}
        for m in my_more:
            if m.get("match_id") in opp_match_ids and m.get("match_id") not in existing_ids:
                h2h.append(m)
                existing_ids.add(m.get("match_id"))
        if len(h2h) >= max_results:
            break

    # === Secondary source: /teams/results with two team_ids ===
    # Flashscore sometimes returns the head-to-head subset when both
    # team_ids are passed in the same query (e.g. team_id=A&team_id=B).
    # The endpoint is unreliable (it usually returns the schedule of
    # only the last team_id, not the intersection), but when it works
    # it gives us a fast lookup. We only ADD matches that contain BOTH
    # team_ids in the same match envelope -- otherwise we would leak
    # unrelated games into the H2H list.
    try:
        url = f"https://{HOST}/api/flashscore/v2/teams/results?team_id={my_team_id}&team_id={opp_team_id}"
        data = _fetch(url)
        if isinstance(data, list):
            existing_ids = {m.get("match_id") for m in h2h}
            for env in data:
                if not isinstance(env, dict):
                    continue
                for m in env.get("matches", []) or []:
                    if not isinstance(m, dict):
                        continue
                    mid = m.get("match_id")
                    if not mid or mid in existing_ids:
                        continue
                    h = m.get("home_team") or {}
                    a = m.get("away_team") or {}
                    h_id = h.get("team_id") if isinstance(h, dict) else None
                    a_id = a.get("team_id") if isinstance(a, dict) else None
                    if {h_id, a_id} != {my_team_id, opp_team_id}:
                        continue  # not a true H2H match, skip
                    row = _parse_match_row(m, my_team_id)
                    if row:
                        h2h.append(row)
                        existing_ids.add(mid)
                if len(h2h) >= max_results:
                    break
    except Exception:
        pass

    return h2h[:max_results]


def fetch_team_results(team_id, my_team_id=None, max_results=5, max_pages=1):
    """Call Flashscore /teams/results?team_id={id} and return last N matches.

    Args:
        team_id: the team whose results to fetch
        my_team_id: which side is "ours" (for win/loss emoji)
        max_results: limit on the number of returned matches (default 5).
            When the caller walks multiple pages (max_pages>1) the function
            returns ALL matches from the visited pages — i.e. the cap
            applies only to the SINGLE-PAGE default. The caller can still
            slice the result with [:max_results] after the walk.
        max_pages: how many pages of the Flashscore results feed to walk
            (default 1 ≈ ~40-45 most recent matches). Set higher for
            deeper history.

    Returns:
        list of dicts (see _parse_match_row) or [] on error.
    """
    if not team_id:
        return []
    flat = []
    for page in range(1, max_pages + 1):
        url = f"https://{HOST}/api/flashscore/v2/teams/results?team_id={team_id}&page={page}"
        data = _fetch_json(url)
        if not isinstance(data, list) or not data:
            break
        for env in data:
            if not isinstance(env, dict):
                continue
            tshort = env.get("name") or ""
            tshort = _short_tournament(tshort) if "_short_tournament" in globals() else tshort
            for m in env.get("matches", []) or []:
                row = _parse_match_row(m, my_team_id or team_id)
                if row:
                    # Augment with tournament from the envelope (env.name)
                    if not row.get("tournament"):
                        row["tournament"] = tshort
                    flat.append(row)
    # Sort by timestamp DESC
    flat.sort(key=lambda x: int(x.get("timestamp", 0) or 0), reverse=True)
    # When walking multiple pages, do NOT cap at max_results — the caller
    # asked for "all matches on max_pages pages". The default 5 stays
    # untouched for single-page callers (the historical default behavior).
    if max_pages > 1:
        return flat
    return flat[:max_results]


def fetch_team_details_for_match(team_id, slug):
    """Call Flashscore /teams/details for stadium info (used in H2H popup header)."""
    if not team_id or not slug:
        return {}
    url = f"https://{HOST}/api/flashscore/v2/teams/details?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    data = _fetch_json(url)
    if not isinstance(data, dict) or data.get("_error"):
        return {}
    return {
        "name": data.get("name") or "",
        "image_path": data.get("image_path") or "",
        "stadium": data.get("stadium") or "",
        "city": data.get("city") or "",
        "capacity": data.get("capacity") or 0,
    }


def fetch_match_venue(match_id):
    """Call Flashscore /matches/details and return the match-specific venue.

    Jul 24 2026: we used to read stadium from /teams/details (which gives
    the team's HOME stadium), but the H2H popup header must show the
    stadium where THIS MATCH is actually being played. The match-level
    venue can differ from the team's home stadium (e.g. Luzern's home
    is Swissporarena, but a specific match may be played at Thermoplan
    Arena). /matches/details exposes this as `venue.{name,city,capacity}`.

    Returns:
        dict {name, city, capacity, referee} or {} on error / missing.
    """
    if not match_id:
        return {}
    url = f"https://{HOST}/api/flashscore/v2/matches/details?match_id={match_id}"
    data = _fetch_json(url)
    if not isinstance(data, dict) or data.get("_error"):
        return {}
    venue = data.get("venue") or {}
    if not isinstance(venue, dict):
        venue = {}
    return {
        "name": venue.get("name") or "",
        "city": venue.get("city") or "",
        "capacity": venue.get("capacity") or 0,
        "referee": data.get("referee") or "",
    }


def fetch_match_h2h_payload(match_id, my_team_id, opp_team_id, my_slug, opp_slug):
    """Build the full H2H + Last Matches payload for the popup.

    Performs (only on click):
        1. /teams/results for BOTH teams        → compute real H2H by
           intersection (matches that involved BOTH teams)
        2. /matches/details for THIS match      → match-specific venue
           (the stadium where this specific match is being played)
        3. /teams/details (fallback)            → team's home stadium,
           used only if /matches/details has no venue.

    Note: We previously tried /matches/h2h?match_id=... but that endpoint
    returns the full match list of the parent tournament, not the head-to-
    head history between the two teams. See fetch_h2h() for details.

    Returns:
        dict with keys: stadium, h2h, last_my, last_opp, error
    """
    payload = {"stadium": {}, "h2h": [], "last_my": [], "last_opp": [], "error": None}
    try:
        # 1. Last matches for both teams (also feeds H2H intersection)
        payload["last_my"] = fetch_team_results(my_team_id, my_team_id=my_team_id, max_results=5)
        payload["last_opp"] = fetch_team_results(opp_team_id, my_team_id=opp_team_id, max_results=5)
        # 2. Real H2H = intersection of both teams' recent results
        payload["h2h"] = fetch_h2h(match_id, max_results=5, my_team_id=my_team_id, opp_team_id=opp_team_id)
        # 3. Match-specific venue (the actual stadium for THIS match)
        venue = fetch_match_venue(match_id)
        # 4. Fallback to team's home stadium if /matches/details had no
        #    venue (older matches, cancelled, etc.)
        if not venue.get("name"):
            my_details = fetch_team_details_for_match(my_team_id, my_slug) or {}
            if not my_details:
                my_details = fetch_team_details_for_match(opp_team_id, opp_slug) or {}
            if my_details:
                venue = {
                    "name": my_details.get("stadium") or "",
                    "city": my_details.get("city") or "",
                    "capacity": my_details.get("capacity") or 0,
                    "referee": "",
                }
        if venue and venue.get("name"):
            payload["stadium"] = venue
    except Exception as e:
        payload["error"] = str(e)
    return payload
