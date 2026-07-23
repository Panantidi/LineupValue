#!/usr/bin/env python3
"""Generic Phase 2 fetch: full Flashscore API data for any country + championship.
Usage: phase2_generic.py <country_name> <championship_name> <output_json_path>
e.g.  phase2_generic.py Albania "Kategoria e Parë" /tmp/albania_kat.json

Fetches: team_details (stadium), squad (from `Total` group), player_details (MV),
last 3 results with lineups (START/SUB + missingPlayers → emoji), and next 3
upcoming fixtures. Writes everything to a single JSON file that
update_caches_generic.py will push to the live cache + SQLite.

Each player carries parallel `last3[]` (participation) and `last3_missing[]`
(absence) arrays. The renderer in lineup_team_view.py picks the right one
based on whether the player START/SUB or was MISSING.
"""
import json, urllib.request, ssl, time, os, sys, urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
KEY = "82f1fc4f2emsh6f172ea91bb5386p1cd344jsndd0fc401e69f"
HOST = "flashscore4.p.rapidapi.com"
HEADERS = {"X-Rapidapi-Key": KEY, "X-Rapidapi-Host": HOST, "User-Agent": "curl/8.5.0", "Accept": "*/*"}

CACHE_DIR = "/home/openclaw/.openclaw/workspace"
LEAGUES_FILE = "/home/openclaw/FormAlert/leagues_data.json"

POS_MAP = {
    "Goalkeepers": "GK", "Goalkeeper": "GK",
    "Defenders": "DF", "Defender": "DF",
    "Midfielders": "MF", "Midfielder": "MF",
    "Forwards": "FW", "Forward": "FW", "Striker": "FW", "Strikers": "FW",
}

# Tournament short name: 2-4 chars used in the Last 3 column header.
# Add new entries as new championships come online.
TOURNAMENT_SHORT = {
    # Albania
    "Abissnet Superiore": "SL",
    "Kategoria e Parë": "1D",
    "Kategoria Superiore": "1D",
    "Albanian Cup": "CUP",
    # Algeria
    "Ligue 1": "L1",
    "Ligue 2": "L2",
    "Algeria Cup": "CUP",
    # Andorra
    "Primera Divisió": "PD",
    "Andorra Cup": "CUP",
    # Argentina
    "Liga Profesional": "LPF",
    "Copa de la Liga Profesional": "LPF",
    "Copa Argentina": "CUP",
    "Trofeo de Campeones": "SC",
    "CONMEBOL Libertadores": "UCL",
    "CONMEBOL Sudamericana": "UEL",
    "CONMEBOL Recopa": "SC",
    # Armenia
    "Armenian Cup": "CUP",
    "Premier League": "PL",  # shared with Azerbaijan
    # Australia
    "A-League": "AL",
    "A-League - Play Offs": "AL",
    "Australia Cup": "CUP",
    "Australian Championship": "CUP",
    # Austria
    "Austrian Bundesliga": "BL",
    "ÖFB-Cup": "CUP",
    "Austrian Cup": "CUP",
    "2. Liga": "L2",
    # Azerbaijan
    "AZERBAIJAN: Premier League": "PL",
    "Azerbaijan Cup": "CUP",
    # Belarus
    "BELARUS: Belarusian Cup": "CUP",
    "Belarusian Cup": "CUP",
    "Vysshaya Liga": "VL",
    # Belgium
    "BELGIUM: Belgian Cup": "CUP",
    "Belgian Cup": "CUP",
    "Jupiler Pro League": "JPL",
    "BELGIUM: Jupiler Pro League": "JPL",
    # Generic
    "Super Cup": "SC",
    "Club Friendly": "FR",
    "WORLD: Club Friendly": "FR",
    "UEFA Champions League": "UCL",
    "UEFA Europa League": "UEL",
    "UEFA Conference League": "ECL",
    "EURO: Conference League - Qualification": "ECLQ",
    "EURO: Europa League - Qualification": "UELQ",
    "EURO: Champions League - Qualification": "UCLQ",
    "World Cup": "WC",
    "EURO": "EURO",
    "League Cup": "LC",
    "FA Cup": "FA",
}

COUNTRY_CODES = {
    "Albania": "al", "Algeria": "dz", "Andorra": "ad", "Argentina": "ar",
    "Armenia": "am", "Australia": "au", "Austria": "at", "Azerbaijan": "az",
    "Bahrain": "bh", "Bangladesh": "bd", "Belarus": "by", "Belgium": "be",
    "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Brazil": "br",
    "Bulgaria": "bg", "Cameroon": "cm", "Canada": "ca", "Chile": "cl",
    "China": "cn", "Colombia": "co", "Costa Rica": "cr", "Croatia": "hr",
    "Cyprus": "cy", "Czech Republic": "cz", "Denmark": "dk", "Ecuador": "ec",
    "Egypt": "eg", "El Salvador": "sv", "England": "gb", "Estonia": "ee",
    "Faroe Islands": "fo", "Finland": "fi", "France": "fr", "Georgia": "ge",
    "Germany": "de", "Ghana": "gh", "Gibraltar": "gi", "Greece": "gr",
    "Guatemala": "gt", "Honduras": "hn", "Hong Kong": "hk", "Hungary": "hu",
    "Iceland": "is", "India": "in", "Indonesia": "id", "Iran": "ir",
    "Iraq": "iq", "Ireland": "ie", "Israel": "il", "Italy": "it",
    "Ivory Coast": "ci", "Jamaica": "jm", "Japan": "jp", "Kazakhstan": "kz",
    "Kenya": "ke", "Kosovo": "xk", "Kuwait": "kw", "Kyrgyzstan": "kg",
    "Latvia": "lv", "Liechtenstein": "li", "Lithuania": "lt",
    "Luxembourg": "lu", "North Macedonia": "mk", "Malaysia": "my",
    "Malta": "mt", "Moldova": "md", "Montenegro": "me", "Morocco": "ma",
    "Mexico": "mx", "Netherlands": "nl", "New Zealand": "nz", "Nigeria": "ng",
    "Norway": "no", "Oman": "om", "Pakistan": "pk", "Panama": "pa",
    "Paraguay": "py", "Peru": "pe", "Philippines": "ph", "Poland": "pl",
    "Portugal": "pt", "Qatar": "qa", "Romania": "ro", "Russia": "ru",
    "Saudi Arabia": "sa", "Scotland": "gb", "Serbia": "rs", "Singapore": "sg",
    "Slovakia": "sk", "Slovenia": "si", "South Africa": "za",
    "South Korea": "kr", "Spain": "es", "Sweden": "se", "Switzerland": "ch",
    "Taiwan": "tw", "Tajikistan": "tj", "Thailand": "th",
    "Trinidad and Tobago": "tt", "Tunisia": "tn", "Turkey": "tr",
    "Turkmenistan": "tm", "Ukraine": "ua", "United Arab Emirates": "ae",
    "Uruguay": "uy", "USA": "us", "Uzbekistan": "uz", "Venezuela": "ve",
    "Vietnam": "vn", "Wales": "gb", "Senegal": "sn",
}


def country_to_flag(name):
    if not name:
        return ""
    code = COUNTRY_CODES.get(name, "")
    if not code:
        return ""
    return f"https://flagcdn.com/w20/{code}.png"


def fetch(url, retries=2):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.3)
    return None


def _missing_emoji(reason):
    """Map a missing-player reason string to an emoji (per the user's spec).
    Returns (emoji, display_text) where display_text is the reason string.
    If reason doesn't match any known category, returns ("", "") — the
    renderer should leave the cell blank for these.
    """
    r = (reason or "").lower()
    if any(kw in r for kw in ['red card']):
        return '🟥', reason
    elif any(kw in r for kw in ['yellow card']):
        return '🟨', reason
    elif any(kw in r for kw in ['loan', 'international', 'duty']):
        return '📄' if 'loan' in r else '🛫', reason
    elif any(kw in r for kw in [
        'injury', 'broken', 'illness', 'health', 'heart',
        'inactive', 'rest', "coach's decision", 'lacking match fitness'
    ]):
        # Injury/illness/Broken etc. map to ❌, but Inactive/Rest/Coach's
        # decision/Lacking Match Fitness get the same emoji treatment as
        # an injury in some leagues — the renderer can leave the cell
        # blank if the reason matches the latter group.
        if any(kw in r for kw in ['injury', 'broken', 'illness', 'health', 'heart']):
            return '❌', reason
        return '', reason  # Inactive / Rest — leave blank
    return '', reason


# Reason tokens that may be appended to a player name by the Flashscore API when
# the player is missing from a match (e.g. "Portillo Juan Knee Injury").
# The full set must match `_missing_emoji()` above. KEEP tokens SINGLE-WORD
# where possible (e.g. "Thigh", not "Thigh Injury") — multi-word reasons like
# "Hamstring Injury" and "Achilles Tendon Injury" are kept because the API
# uses them verbatim, but anything that can be expressed as a single word
# (body part, surgery, etc.) is stored that way so the strip loop can
# match against a single token without false negatives.
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
    "Muscle", "Thigh", "Calf", "Shoulder", "Groin", "Knee", "Hamstring",
    "Achilles", "Achilles Tendon", "Ankle", "Foot", "Hip", "Neck",
    "Wrist", "Hand", "Finger", "Back", "Rib", "Toe", "Elbow", "Leg", "Arm",
    "Injury", "Illness", "Surgery", "Operation", "Rest",
    "Yellow Cards", "Yellow Card", "Red Card",
    "Suspended", "Suspension", "Banned",
    "Personal Reasons", "Private Reasons", "Family Reasons",
    "Loan agreement", "International duty",
    "Not in squad", "Not in match squad", "Coach's decision",
    "Inactive", "Resting", "Disciplinary",
)

# Date patterns that Flashscore appends after the reason
# (e.g. "Hamstring Injury 01.08.2026"). Match the trailing date.
_DATE_PATTERN_RE = None  # lazy-compiled
def _date_pattern():
    global _DATE_PATTERN_RE
    if _DATE_PATTERN_RE is None:
        import re as _re
        # dd.mm.yyyy or dd/mm/yyyy or dd-mm-yyyy, anywhere in the string
        _DATE_PATTERN_RE = _re.compile(
            r'\s+\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\s*$'
        )
    return _DATE_PATTERN_RE


def _strip_missing_reason_suffix(name):
    """Strip a trailing reason keyword (and optional date) from a player name.

    The Flashscore API sometimes returns `name` as
    `"<Surname> <FirstName> <Reason> [<Date>]"` for missing players, e.g.:

        "Estêvão Hamstring Injury 01.08.2026"     → "Estêvão"
        "Gittens Jamie Hamstring Injury 01.08.2026" → "Gittens Jamie"
        "Wesley Franca Muscle Injury 02.08.2026"  → "Wesley Franca"
        "Joelinton Thigh"                          → "Joelinton"
        "Miley Lewis Broken Leg 02.09.2026"        → "Miley Lewis"
        "Hollerbach Benedict Achilles Tendon Injury 02.08.2026"
                                                    → "Hollerbach Benedict"
        "Agyekum Lawrence Shoulder"                → "Agyekum Lawrence"
        "Estêvão"                                  → "Estêvão"  (no reason)
        "Neymar"                                   → "Neymar"    (no reason)

    The reason is delivered separately via `missingPlayers[].reason` and
    rendered as an emoji + tooltip — it must NOT appear next to the name.

    Algorithm:
      1. Strip any trailing date first (e.g. " 01.08.2026").
      2. While the last 1-4 tokens match a known reason token, strip them.
      3. If we strip everything (e.g. name = "Thigh"), restore the original.
      4. Otherwise return the cleaned name (1+ tokens).

    This is safe for single-word player names like "Estêvão" because the
    reason tokens never start with a capital letter and never coincide
    with real names in our dataset. If a future name conflicts, the
    worst case is the reason NOT being stripped (we keep the original).
    """
    if not name:
        return name
    original = name
    # 1. Strip trailing date
    name = _date_pattern().sub('', name).strip()
    parts = name.split()
    if not parts:
        return original  # safety: don't return empty
    # 2. Strip trailing reason tokens (try longest first)
    for _ in range(4):  # max 4 reason words (e.g. "Cruciate Ligament Injury Resting")
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


# Module-level side-channel for `last3_missing`.
# Maps (match_id, player_id) → {emoji, reason, side}.
# `process_team` reads from this after `fetch_lineups_for_match` to attach
# missing data to the right player + match position.
_last_missing = {}


def fetch_squad(team_id, slug):
    """Fetch squad from /teams/squad, picking the `Total` group if present.
    Response: list of groups like
        [{tab_name: "Albanian Cup", list: [{name: "Goalkeepers", players: [...]}, ...]},
         {tab_name: "Superliga", ...},
         {tab_name: "Total", ...}]
    ALWAYS pick the group with tab_name == "Total" (covers all competitions).
    If Total is missing, fall back to the first non-empty group.
    Skip the `Coach` section (its `players: []` is always empty per API).
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/squad?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    data = fetch(url)
    if not data:
        return None
    groups = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(groups, list) or not groups:
        return []
    # Prefer the Total group — aggregated across all competitions
    best = None
    for g in groups:
        if isinstance(g, dict) and g.get("tab_name") == "Total" and g.get("list"):
            best = g
            break
    if not best:
        # Fallback: first non-empty group
        for g in groups:
            if isinstance(g, dict) and g.get("list"):
                best = g
                break
    if not best:
        return []
    players = []
    for section in best["list"]:
        if not isinstance(section, dict):
            continue
        pos_full = section.get("name", "")
        # Skip Coach section — it's rendered separately, and its players
        # list is always [] in this API.
        if pos_full == "Coach":
            continue
        pos = POS_MAP.get(pos_full, pos_full[:2].upper())
        for p in section.get("players", []):
            pid = p.get("player_id")
            name = p.get("name")
            if not pid or not name:
                continue
            # Strip a reason suffix that the API sometimes appends to
            # `name` for missing players (e.g. "Portillo Juan Knee
            # Injury" → "Portillo Juan"). The reason itself is preserved
            # in `last3_missing[].reason`.
            name = _strip_missing_reason_suffix(name)
            mv = p.get("market_value")
            players.append({
                "player_id": pid,
                "name": name,
                "number": p.get("number", ""),
                "country": p.get("country_name", ""),
                "country_flag": country_to_flag(p.get("country_name", "")),
                # age comes as INT — str().isdigit() or it crashes
                "age": int(p["age"]) if str(p.get("age", "")).isdigit() else None,
                "position": pos,
                "market_value": mv if mv else "",
                "apps": int(p["matches_played"]) if str(p.get("matches_played", "")).isdigit() else 0,
                "min": int(p["minutes_played"]) if str(p.get("minutes_played", "")).isdigit() else 0,
                "goals": int(p["goals_scored"]) if str(p.get("goals_scored", "")).isdigit() else 0,
                "assists": int(p["assists"]) if str(p.get("assists", "")).isdigit() else 0,
                "yellow_cards": int(p["yellow_cards"]) if str(p.get("yellow_cards", "")).isdigit() else 0,
                "red_cards": int(p["red_cards"]) if str(p.get("red_cards", "")).isdigit() else 0,
                "player_url": p.get("player_url", ""),
                "tournament": best.get("tab_name", ""),
            })
    return players


def fetch_player_details(player):
    purl = player.get("player_url", "")
    if not purl:
        return
    full_url = f"https://{HOST}/api/flashscore/v2/players/details?player_url={urllib.parse.quote(purl, safe='/?=')}"
    d = fetch(full_url)
    if not d or not isinstance(d, dict):
        return
    mv = d.get("market_value")
    if mv and (isinstance(mv, (int, float)) or str(mv).strip()):
        player["market_value"] = mv
    img = d.get("image_path")
    if img:
        player["image_path"] = img
    time.sleep(0.2)


def _norm_team(t_):
    """Flatten home_team/away_team dict → {id, name, slug}."""
    if isinstance(t_, dict):
        return {
            "id": t_.get("team_id"),
            "name": t_.get("name") or t_.get("short_name") or "",
            "slug": "",
        }
    return {"id": None, "name": str(t_) if t_ else "", "slug": ""}


def _extract_score(m):
    """Score is a NESTED dict: m['scores'] = {'home': 2, 'away': 1}.
    Try ft_score / flat home_score first, fall back to scores.home/away."""
    score = m.get("ft_score") or m.get("score")
    if not score:
        sh = m.get("home_score")
        sa = m.get("away_score")
        if isinstance(sh, int) and isinstance(sa, int):
            score = f"{sh}-{sa}"
    if not score:
        scores_obj = m.get("scores")
        if isinstance(scores_obj, dict):
            sh = scores_obj.get("home")
            sa = scores_obj.get("away")
            if isinstance(sh, int) and isinstance(sa, int):
                score = f"{sh}-{sa}"
    return str(score) if score else ""


def fetch_results(team_id):
    """Fetch last 3 PLAYED matches from /teams/results.
    Response: list of tournaments, each with matches[].
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/results?team_id={team_id}&page=1"
    data = fetch(url)
    if not data:
        return []
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(rows, list):
        return []
    all_matches = []
    for t in rows:
        if not isinstance(t, dict):
            continue
        tname = t.get("full_name") or t.get("name", "")
        tshort = TOURNAMENT_SHORT.get(t.get("name", "") or tname, t.get("name", "")[:3].upper() or "—")
        for m in t.get("matches", []):
            if not isinstance(m, dict):
                continue
            mid = m.get("match_id")
            ts = m.get("timestamp") or m.get("start_timestamp") or 0
            date_str = ""
            if ts:
                try:
                    date_str = datetime.fromtimestamp(int(ts)).strftime("%d/%m")
                except Exception:
                    pass
            all_matches.append({
                "match_id": mid,
                "date": date_str,
                "timestamp": int(ts) if ts else 0,
                "tournament_name_short": tshort,
                "tournament_name_full": tname,
                "home_team": _norm_team(m.get("home_team")),
                "away_team": _norm_team(m.get("away_team")),
                "score": _extract_score(m),
            })
    all_matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_matches[:3]


def fetch_fixtures(team_id):
    """Fetch next 3 UPCOMING matches from /teams/fixtures.
    Same envelope as /teams/results but future matches have no 'scores' field.
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
    data = fetch(url)
    if not data:
        return []
    rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(rows, list):
        return []
    all_fixtures = []
    for t in rows:
        if not isinstance(t, dict):
            continue
        tname = t.get("full_name") or t.get("name", "")
        tshort = TOURNAMENT_SHORT.get(t.get("name", "") or tname, t.get("name", "")[:3].upper() or "—")
        for m in t.get("matches", []):
            if not isinstance(m, dict):
                continue
            mid = m.get("match_id")
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
            all_fixtures.append({
                "match_id": mid,
                "date": date_str,
                "time": time_str,
                "timestamp": int(ts) if ts else 0,
                "tournament_name_short": tshort,
                "tournament_name_full": tname,
                "home_team": _norm_team(m.get("home_team")),
                "away_team": _norm_team(m.get("away_team")),
            })
    # Future matches: sort ASC so the closest match is first.
    all_fixtures.sort(key=lambda x: x.get("timestamp", 0))
    return all_fixtures[:3]


def fetch_lineups_for_match(match_id, team_id):
    """Fetch lineups for a match, returning {player_id: "START"|"SUB"}.
    Also populates the module-level `_last_missing` side-channel so
    `process_team` can attach missing-data info to the right player+match
    position in the cache.
    """
    if not match_id:
        return {}
    url = f"https://{HOST}/api/flashscore/v2/matches/match/lineups?match_id={match_id}"
    d = fetch(url)
    if not d:
        return {}
    lineups = d if isinstance(d, list) else (d.get("data") if isinstance(d, dict) else [])
    if not isinstance(lineups, list):
        return {}
    result = {}
    for lu in lineups:
        if not isinstance(lu, dict):
            continue
        side = lu.get("side", "")
        starting = lu.get("startingLineups") or []
        bench = lu.get("substitutes") or []
        for p in starting:
            if isinstance(p, dict):
                pid = str(p.get("player_id") or p.get("id", ""))
                if pid:
                    result[pid] = "START"
        for p in bench:
            if isinstance(p, dict):
                pid = str(p.get("player_id") or p.get("id", ""))
                if pid:
                    result[pid] = "SUB"
        # Collect missing players for this side
        for mp in lu.get("missingPlayers") or []:
            if not isinstance(mp, dict):
                continue
            pid = str(mp.get("player_id") or "")
            if not pid:
                continue
            reason = mp.get("reason", "") or ""
            emoji, _ = _missing_emoji(reason)
            _last_missing[pid] = {"emoji": emoji, "reason": reason, "side": side}
    return result


def fetch_team_details(team_id, slug):
    """Fetch /teams/details: stadium, city, capacity (string).
    Coach data is NOT available from this endpoint — see squad fallback below.
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/details?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    d = fetch(url)
    if not d or not isinstance(d, dict):
        return {"stadium": "", "city": "", "capacity": 0}
    return {
        "stadium": d.get("stadium", "") or "",
        "city": d.get("city", "") or "",
        "capacity": d.get("capacity", 0) or 0,
    }


def process_team(team_id, slug, team_name, our_team_id):
    print(f"[{team_name}] team_details...", flush=True)
    details = fetch_team_details(team_id, slug)
    print(f"  stadium: '{details['stadium']}', city: '{details['city']}'", flush=True)

    print(f"[{team_name}] squad...", flush=True)
    players = fetch_squad(team_id, slug)
    if players is None:
        return None
    empty = {
        "team_id": team_id, "name": team_name, "slug": slug,
        "players": [], "matches": [], "fixtures": [],
        "stadium": details["stadium"], "city": details["city"], "capacity": details["capacity"],
    }
    if not players:
        return empty
    print(f"  {len(players)} players", flush=True)

    print(f"  player_details...", flush=True)
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(fetch_player_details, players))

    print(f"  results...", flush=True)
    matches = fetch_results(team_id)
    # Derive side: drives the Last 3 cell color (win/draw/loss).
    for m in matches:
        home_id = m.get("home_team", {}).get("id") if isinstance(m.get("home_team"), dict) else None
        m["side"] = "home" if str(home_id) == str(our_team_id) else "away"
    print(f"  {len(matches)} matches", flush=True)

    # Build per-player last3 by joining lineups (3 most recent matches) with squad IDs.
    squad_ids = {p["player_id"] for p in players}
    last3_per_player = {p["player_id"]: ["", "", ""] for p in players}
    last3_missing_per_player = {p["player_id"]: [None, None, None] for p in players}
    for i, m in enumerate(matches):
        if not m.get("match_id"):
            continue
        all_lineups = fetch_lineups_for_match(m["match_id"], our_team_id)
        # Look up missing side-channel — keyed by player_id
        for pid, status in all_lineups.items():
            if pid in squad_ids:
                last3_per_player[pid][i] = status
                # If player START/SUB, clear the missing slot (participation wins)
                if pid in _last_missing:
                    del _last_missing[pid]
        # Now any remaining _last_missing entries that match a squad player
        # are missing (didn't appear in starting or bench)
        for pid in list(_last_missing.keys()):
            if pid in squad_ids:
                last3_missing_per_player[pid][i] = _last_missing[pid]
        ours = sum(1 for pid in all_lineups if pid in squad_ids)
        ours_missing = sum(1 for pid in _last_missing if pid in squad_ids)
        print(f"  match {i+1}: {len(all_lineups)} lineups, {ours} ours, {ours_missing} missing", flush=True)
        # IMPORTANT: clear _last_missing between matches so they don't bleed
        _last_missing.clear()
    for p in players:
        p["last3"] = last3_per_player.get(p["player_id"], ["", "", ""])
        p["last3_missing"] = last3_missing_per_player.get(p["player_id"], [None, None, None])

    print(f"  fixtures...", flush=True)
    fixtures = fetch_fixtures(team_id)
    print(f"  {len(fixtures)} upcoming fixtures", flush=True)

    return {
        "team_id": team_id,
        "name": team_name,
        "slug": slug,
        "players": players,
        "matches": matches,
        "fixtures": fixtures,
        "stadium": details["stadium"],
        "city": details["city"],
        "capacity": details["capacity"],
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: phase2_generic.py <country_name> <championship_name> <output_path>")
        sys.exit(1)
    country_name = sys.argv[1]
    championship = sys.argv[2]
    output_path = sys.argv[3]

    ld = json.load(open(LEAGUES_FILE))
    teams = ld.get(country_name, {}).get(championship, [])
    print(f"Total teams in {country_name} / {championship}: {len(teams)}", flush=True)
    results = []
    for t in teams:
        tid = t["id"]
        slug = t.get("slug") or tid
        name = t["name"]
        res = process_team(tid, slug, name, tid)
        if res:
            results.append(res)
        time.sleep(0.3)
    with open(output_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(results)} teams to {output_path}", flush=True)


if __name__ == "__main__":
    main()
