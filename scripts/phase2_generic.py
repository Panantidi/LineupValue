#!/usr/bin/env python3
"""Phase 2 generic: full data via Flashscore API for a single championship.
Usage: phase2_generic.py <country_name> <championship_name> <output_path>
e.g.  phase2_generic.py Albania "Kategoria e Parë" /tmp/albania_kat.json
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

TOURNAMENT_SHORT = {
    "Abissnet Superiore": "SL",
    "Kategoria e Parë": "1D",
    "Kategoria Superiore": "1D",
    "Albanian Cup": "CUP",
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
    "Luxembourg": "lu", "North Macedonia": "mk", "Macao": "mo", "Malaysia": "my",
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


# Reason keywords that the API sometimes appends to a player's `name` when
# the player is missing from a match (e.g. "Portillo Juan Knee Injury").
# The full set must match `_missing_emoji()` + the skill's reason-emoji map.
_REASON_TOKENS = (
    "Knee Injury", "Muscle Injury", "Hamstring Injury", "Achilles Tendon Injury",
    "Lower Back Injury", "Head Injury", "Groin Injury", "Ankle Injury",
    "Thigh Injury", "Toe Injury", "Foot Injury",
    "Injury", "Illness", "Health problems", "Heart Problems",
    "Red Card", "Yellow Cards", "Yellow Card",
    "Loan agreement", "International duty",
)

def _strip_missing_reason_suffix(name):
    """If a reason keyword appears as a trailing token(s) at the end of
    `name`, strip it. Returns the cleaned name unchanged if no match.
    The expected API format is "Surname FirstName [Reason]" — i.e. exactly
    2 + N tokens for a normal player, 3 + N tokens when a reason was appended.
    We only strip when the result is still a plausible name (≥ 2 tokens)."""
    if not name:
        return name
    parts = name.split()
    if len(parts) <= 2:
        return name  # too short to safely strip
    # Try longest reason tokens first
    for reason in sorted(_REASON_TOKENS, key=len, reverse=True):
        r_parts = reason.split()
        if len(parts) > len(r_parts) and parts[-len(r_parts):] == r_parts:
            cleaned = " ".join(parts[:-len(r_parts)])
            if len(cleaned.split()) >= 2:
                return cleaned
    return name


def fetch_squad(team_id, slug):
    """Fetch squad with priority to "Total" group (all matches combined).

    Response is a list of groups, each with `tab_name` (e.g. "Albanian Cup",
    "Superliga", "Total") and `list` (sections like Goalkeepers/Defenders/...).

    Always prefer the "Total" group — it has stats aggregated across ALL
    competitions the team played in, not just one championship. This is
    what the user wants to see: every player who ever appeared for the team
    across all competitions, with their combined apps/starts/subs.
    """
    url = f"https://{HOST}/api/flashscore/v2/teams/squad?team_url=%2Fteam%2F{slug}%2F{team_id}%2F"
    data = fetch(url)
    if not data:
        return None
    groups = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not isinstance(groups, list) or not groups:
        return []
    players = []
    # Priority 1: "Total" group (all competitions combined)
    best = None
    for g in groups:
        if isinstance(g, dict) and g.get("tab_name") == "Total" and g.get("list"):
            best = g
            break
    # Priority 2: first non-empty group (fallback for teams that only have one tab)
    if not best:
        for g in groups:
            if isinstance(g, dict) and g.get("list"):
                best = g
                break
    if best:
        for section in best["list"]:
            if not isinstance(section, dict):
                continue
            pos_full = section.get("name", "")
            if pos_full == "Coach":
                # Skip Coach group (Coach is rendered separately, see Coach schema)
                continue
            pos = POS_MAP.get(pos_full, pos_full[:2].upper())
            for p in section.get("players", []):
                pid = p.get("player_id")
                name = p.get("name")
                if not pid or not name:
                    continue
                # Strip a reason suffix that the API sometimes appends to
                # `name` for missing/injured players (e.g. "Portillo Juan Knee Injury"
                # → "Portillo Juan"). The reason itself is already stored separately
                # in `last3_missing` and must NOT show up next to the player's name.
                name = _strip_missing_reason_suffix(name)
                mv = p.get("market_value")
                players.append({
                    "player_id": pid,
                    "name": name,
                    "number": p.get("number", ""),
                    "country": p.get("country_name", ""),
                    "country_flag": country_to_flag(p.get("country_name", "")),
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


def fetch_results(team_id):
    """Fetch last 3 PLAYED matches from /teams/results."""
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
            home = m.get("home_team") or {}
            away = m.get("away_team") or {}

            def _norm(t_):
                if isinstance(t_, dict):
                    return {
                        "id": t_.get("team_id"),
                        "name": t_.get("name") or t_.get("short_name") or "",
                        "slug": "",
                    }
                return {"id": None, "name": str(t_) if t_ else "", "slug": ""}

            h = _norm(home)
            a = _norm(away)
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
                "home_team": h,
                "away_team": a,
                "score": str(score) if score else "",
            })
    all_matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_matches[:3]


def fetch_fixtures(team_id):
    """Fetch next 3 UPCOMING matches from /teams/fixtures.
    Response: list of tournaments, each with matches[].
    No scores (future matches).
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
            home = m.get("home_team") or {}
            away = m.get("away_team") or {}

            def _norm(t_):
                if isinstance(t_, dict):
                    return {
                        "id": t_.get("team_id"),
                        "name": t_.get("name") or t_.get("short_name") or "",
                        "slug": "",
                    }
                return {"id": None, "name": str(t_) if t_ else "", "slug": ""}

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
                "home_team": _norm(home),
                "away_team": _norm(away),
            })
    all_fixtures.sort(key=lambda x: x.get("timestamp", 0))
    return all_fixtures[:3]


def _missing_emoji(reason):
    """Map a missing-player reason string to an emoji (per the user's spec).
    Returns (emoji, display_text) where display_text is the reason string.
    If reason doesn't match a known category, returns ("", "") and the cell
    stays empty (no emoji, no noise in UI).
    """
    if not reason:
        return ("", "")
    r = reason.lower()
    # Injury / Broken / Illness → red X
    injury_kw = ("injury", "broken", "illness", "health", "heart")
    if any(kw in r for kw in injury_kw):
        return ("❌", reason)
    # Red card → red square
    if "red card" in r:
        return ("🟥", reason)
    # Yellow cards → yellow square
    if "yellow card" in r:
        return ("🟨", reason)
    # Loan agreement → document
    if "loan" in r:
        return ("📄", reason)
    # International duty → airplane
    if "international" in r or "duty" in r:
        return ("🛫", reason)
    # Inactive / Rest / Coach's decision / Lacking Match Fitness → no emoji (intentionally blank)
    return ("", "")


def fetch_lineups_for_match(match_id, team_id):
    """Fetch lineups for one match.

    Returns a dict: `{player_id: "START"|"SUB"}` for players in our squad.
    Also writes a side-effect dict via a closure-free approach: missing
    players (filtered to our team_id) are stored in a module-level
    `_last_missing[match_id] = {player_id: {emoji, reason}}` so the caller
    can attach them to the match in cache.
    """
    global _last_missing
    if not match_id:
        return {}
    url = f"https://{HOST}/api/flashscore/v2/matches/match/lineups?match_id={match_id}"
    d = fetch(url)
    if not d:
        _last_missing[match_id] = {}
        return {}
    lineups = d if isinstance(d, list) else (d.get("data") if isinstance(d, dict) else [])
    if not isinstance(lineups, list):
        _last_missing[match_id] = {}
        return {}
    result = {}
    missing_for_our_team = {}
    for lu in lineups:
        if not isinstance(lu, dict):
            continue
        # Detect which side is "our" team. The API does not give a clean
        # `team_id` field on the lineup envelope — it gives `side` ("home"/"away").
        # We match by checking startingLineups player_ids against our squad
        # file (if available) or by always including both sides' missing.
        # For simplicity we collect BOTH sides' missing, and let the cache
        # filter by player_id against our squad (the renderer already maps
        # player_id → player, so unknown player_ids are ignored).
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
        for p in lu.get("missingPlayers") or []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("player_id") or p.get("id", ""))
            reason = p.get("reason", "") or ""
            if not pid:
                continue
            emoji, _ = _missing_emoji(reason)
            if emoji:
                missing_for_our_team[pid] = {
                    "emoji": emoji,
                    "reason": reason,
                    "side": side,
                }
    _last_missing[match_id] = missing_for_our_team
    return result


# Side-channel store for missing players populated by fetch_lineups_for_match.
# Read by process_team() after fetching lineups for a match.
_last_missing = {}


def fetch_team_details(team_id, slug):
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
    if not players:
        return {"team_id": team_id, "name": team_name, "slug": slug, "players": [], "matches": [], "stadium": details["stadium"], "city": details["city"], "capacity": details["capacity"]}
    print(f"  {len(players)} players", flush=True)

    print(f"  player_details...", flush=True)
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(fetch_player_details, players))

    print(f"  results...", flush=True)
    matches = fetch_results(team_id)
    for m in matches:
        home_id = m.get("home_team", {}).get("id") if isinstance(m.get("home_team"), dict) else None
        if str(home_id) == str(our_team_id):
            m["side"] = "home"
        else:
            m["side"] = "away"

    print(f"  fixtures...", flush=True)
    fixtures = fetch_fixtures(team_id)
    print(f"  {len(fixtures)} upcoming fixtures", flush=True)
    print(f"  {len(matches)} matches", flush=True)

    squad_ids = {p["player_id"] for p in players}
    last3_per_player = {p["player_id"]: ["", "", ""] for p in players}
    # parallel arrays: per player, per match, list of {emoji, reason} for missing
    # entries. Empty list = no missing status. The renderer concatenates
    # emoji+reason into the cell (emoji inline, reason in data-tooltip).
    last3_missing = {p["player_id"]: [None, None, None] for p in players}
    for i, m in enumerate(matches):
        if not m.get("match_id"):
            continue
        all_lineups = fetch_lineups_for_match(m["match_id"], our_team_id)
        for pid, status in all_lineups.items():
            if pid in squad_ids:
                last3_per_player[pid][i] = status
        # Capture missing from the side channel populated by fetch_lineups_for_match
        mp = _last_missing.get(m["match_id"], {})
        for pid, info in mp.items():
            if pid in squad_ids:
                last3_missing[pid][i] = info
        print(f"  match {i+1}: {len(all_lineups)} lineups, {sum(1 for pid in all_lineups if pid in squad_ids)} ours, {sum(1 for pid in mp if pid in squad_ids)} missing", flush=True)
    for p in players:
        p["last3"] = last3_per_player.get(p["player_id"], ["", "", ""])
        p["last3_missing"] = last3_missing.get(p["player_id"], [None, None, None])

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
