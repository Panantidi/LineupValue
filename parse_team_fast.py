#!/usr/bin/env python3
"""Fast HTTP-based team data fetcher for Soccerway."""
import asyncio, json, re, sys, time, os
from typing import List, Dict, Any
import httpx
from bs4 import BeautifulSoup

BASE = "https://www.soccerway.com"
CACHE_DIR = "/home/openclaw/.openclaw/workspace"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
POS_MAP = {"Goalkeeper": "GK", "Defender": "DF", "Midfielder": "MF", "Forward": "FW"}
COMP_MAP = {
    "premier league": "PL", "bundesliga": "BL", "2. bundesliga": "B2",
    "ligue 1": "L1", "serie a": "SA", "laliga": "LL", "la liga": "LL",
    "eredivisie": "ERE", "eliteserien": "ELT", "allsvenskan": "ALL",
    "superliga": "SUP", "superligaen": "SUP", "jupiler pro league": "JPL",
    "liga portugal": "LGP", "super league": "SL", "mls": "MLS",
    "major league soccer": "MLS", "vysshaya liga": "VYS",
    "veikkausliiga": "VEI", "a-league": "ALE", "champions league": "CL",
    "champions league - qualification": "CLQ", "europa league": "EL",
    "conference league": "ECL", "efbet league": "EBL", "j1 league": "J1L",
    "concacaf champions cup": "CCL", "leagues cup": "LGC",
    "dfb pokal": "DFB", "fa cup": "FA", "coupe de france": "CDF",
    "copa del rey": "CDR", "coppa italia": "COI", "knvb beker": "KNVB",
    "belgian cup": "BCP", "nm cup": "NMC", "landspokal cup": "LPC",
    "swiss cup": "SWC", "taca de portugal": "TDP", "belarusian cup": "BLC",
    "liiga cup": "LIC", "suomen cup": "SUC", "league cup": "LC",
    "efl cup": "LC", "club friendlies": "FR", "friendlies": "FR",
    "friendly": "FR", "club friendly": "FR", "world championship": "WC",
    "atlantic cup": "FR", "fifa intercontinental cup": "FIC", "super cup": "SCP",
}

def _comp_code(name: str) -> str:
    if not name: return "UNK"
    low = name.lower()
    for k, v in COMP_MAP.items():
        if k in low: return v
    return "UNK"

async def fetch_squad_page_http(team_id: str, team_slug: str) -> str:
    if not team_slug: raise ValueError("team_slug required")
    url = f"{BASE}/team/{team_slug}/{team_id}/squad/"
    async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as c:
        r = await c.get(url); r.raise_for_status(); return r.text

def _extract_initial_feeds(html: str) -> dict:
    feeds = {}
    p = re.compile(r'cjs\.initialFeeds\[(["\'])([^"\']+)\1\]\s*=\s*\{\s*data\s*:\s*`([^`]*)`', re.DOTALL)
    for m in p.finditer(html):
        feeds[m.group(2)] = m.group(3)
    return feeds

def _parse_field(record: str) -> dict:
    out = {}
    for part in record.split("\u00ac"):
        if "\u00f7" not in part: continue
        code, _, val = part.partition("\u00f7")
        out[code.strip()] = val.strip()
    return out

def parse_summary_results(data: str, team_id: str, team_name: str = "", team_slug: str = "", limit: int = 6) -> list:
    if not data: return []
    records = data.split("~")
    matches = []
    current_tournament = ""
    for rec in records:
        if not rec.strip(): continue
        if rec.startswith("SA"): continue
        fields = _parse_field(rec)
        if "ZA" in fields:
            current_tournament = fields.get("ZK") or fields.get("ZY") or ""
            continue
        if "AA" not in fields: continue
        left_id = fields.get("PY", "")
        right_id = fields.get("PX", "")
        if not left_id and not right_id: continue
        our_side = "left" if left_id == team_id else ("right" if right_id == team_id else None)
        if our_side is None: continue
        ts = fields.get("AD", "")
        date = ""; kickoff = ""
        if ts and ts.isdigit():
            try:
                dt = time.gmtime(int(ts))
                date = time.strftime("%d.%m", dt)
                kickoff = time.strftime("%Y-%m-%dT%H:%M", dt)
            except: pass
        # Parse scores - AH=home goals, AG=away goals
        # AH = home goals, AG = away goals
        home_score = fields.get("AH") or fields.get("AS") or fields.get("AZ") or ""
        away_score = fields.get("AG") or ""
        
        # Get team names: AF = home team full name, AE = away team full name
        home_team_name = fields.get("AF", "") or ""
        away_team_name = fields.get("AE", "") or ""
        tournament = _comp_code(current_tournament) if current_tournament else "UNK"
        mid = fields.get("AA", "")
        url = f"{BASE}/match/{fields.get('WV','')}-{left_id}/{fields.get('WU','')}-{right_id}/?mid={mid}".replace("?-", "-").replace("--", "-")
        # Format score as "HomeTeam 2-1 AwayTeam"
        if home_score and away_score:
            score = f"{home_team_name} {home_score}-{away_score} {away_team_name}" if home_team_name and away_team_name else f"{home_score}-{away_score}"
        else:
            score = ""
        matches.append({"date": date, "tournament": tournament, "tournament_name": current_tournament,
                        "mid": mid, "url": url, "score": score, "home_team": home_team_name,
                        "away_team": away_team_name, "kickoff": kickoff})
        if len(matches) >= limit: break
    return matches

async def _fetch_one_profile(client, url):
    try:
        r = await client.get(url, timeout=15.0)
        if r.status_code != 200: return url, "", ""
        soup = BeautifulSoup(r.text, "html.parser")
        spans = soup.select('span[data-testid="wcl-scores-simple-text-01"]')
        pos = ""; mv = ""
        mv_re = re.compile(r"\u20ac[\d.,]+\s*[mMkK]")
        for sp in spans:
            t = sp.get_text(strip=True)
            if t in POS_MAP: pos = POS_MAP[t]; break
        for sp in spans:
            t = sp.get_text(strip=True)
            if mv_re.match(t): mv = t; break
        return url, pos, mv
    except Exception:
        return url, "", ""

async def enrich_players_http(players: list, concurrency: int = 8) -> list:
    targets = []
    for i, p in enumerate(players):
        path = p.get("profile_path") or ""
        if path:
            url = path if path.startswith("http") else f"{BASE}{path}"
            targets.append((i, url))
    if not targets: return players
    sem = asyncio.Semaphore(concurrency)
    async def limited(c, u):
        async with sem: return await _fetch_one_profile(c, u)
    async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as c:
        results = await asyncio.gather(*[limited(c, u) for _, u in targets])
    by_url = {u: (p, m) for u, p, m in results}
    for i, u in targets:
        pos, mv = by_url.get(u, ("", ""))
        if pos: players[i]["position"] = pos
        if mv: players[i]["market_value"] = mv
    return players

def parse_squad_html_local(html: str, team_id: str):
    sys.path.insert(0, "/home/openclaw/FormAlert")
    from soccerway_parser import parse_squad_html
    players_raw, coach_name, stadium = parse_squad_html(html, team_id)
    out = []
    for p in players_raw:
        d = dict(p) if isinstance(p, dict) else vars(p)
        for old, new in {"minutes": "min", "goals": "goal", "assists": "assist",
                         "yellow_cards": "yellow_card", "red_cards": "red_card",
                         "player_url": "profile_path"}.items():
            if old in d and new not in d: d[new] = d.pop(old)
        d.setdefault("last3", ["-", "-", "-"])
        d.setdefault("last3_missing", [None, None, None])
        d.setdefault("last3_captain", [False, False, False])
        out.append(d)
    return out, coach_name, stadium

def _copy_existing_last3(new_players, old_cache):
    sys.path.insert(0, "/home/openclaw/FormAlert")
    from fetch_team import _copy_existing_last3_fields
    return _copy_existing_last3_fields(new_players, old_cache)

async def fetch_team_fast(team_id, team_name, team_slug, coach_nat="", stadium=""):
    cache_path = f"{CACHE_DIR}/_live_cache_{team_id}.json"
    existing = {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f: existing = json.load(f)
    except: pass

    t0 = time.time()
    print(f"[1/5 HTTP] Squad: {team_name}...")
    html = await fetch_squad_page_http(team_id, team_slug)
    print(f"  {len(html)} bytes in {time.time()-t0:.2f}s")
    players, coach_name, stadium_from_page = parse_squad_html_local(html, team_id)
    if not stadium: stadium = stadium_from_page
    print(f"  {len(players)} players, coach={coach_name!r}, stadium={stadium!r}")
    if not players: raise RuntimeError("0 players parsed")

    t1 = time.time()
    print(f"[2/5 HTTP] Enriching {len(players)} players (parallel HTTP)...")
    players = await enrich_players_http(players, concurrency=8)
    enriched = sum(1 for p in players if p.get("position") or p.get("market_value"))
    print(f"  Enriched: {enriched}/{len(players)} in {time.time()-t1:.2f}s")

    players = _copy_existing_last3(players, existing)
    cache = {"team": {"id": team_id, "name": team_name, "slug": team_slug},
             "coach": {"name": coach_name, "nationality": coach_nat},
             "stadium": stadium, "players": players,
             "_cached_at": time.time(), "last_updated": time.time()}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print("  [saved enrichment]")

    t2 = time.time()
    print(f"[3/5 HTTP] Matches from cjs.initialFeeds...")
    feeds = _extract_initial_feeds(html)
    matches = parse_summary_results(feeds.get("summary-results", ""), team_id, team_name, team_slug, limit=6)
    print(f"  {len(matches)} matches in {time.time()-t2:.2f}s")
    if len(matches) < 3: raise RuntimeError(f"only {len(matches)} matches; need >=3")
    matches = matches[:3]

    t3 = time.time()
    print(f"[4/5 PW] Lineups for {len(matches)} matches...")
    
    # Check lineups cache first
    lineups_cache_dir = f"{CACHE_DIR}/lineups_cache"
    os.makedirs(lineups_cache_dir, exist_ok=True)
    
    # Try to load lineups from cache
    cached_lineups = []
    matches_to_fetch = []
    matches_to_fetch_indices = []
    
    for i, m in enumerate(matches):
        mid = m.get("mid", "")
        cache_file = f"{lineups_cache_dir}/{team_id}_{mid}.json"
        if mid and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_lineup = json.load(f)
                    # Check if cache is fresh (within 24 hours)
                    if time.time() - cached_lineup.get("_cached_at", 0) < 86400:
                        cached_lineups.append((i, cached_lineup))
                        print(f"    {m['date']}: using cached lineups")
                        continue
            except:
                pass
        matches_to_fetch.append(m)
        matches_to_fetch_indices.append(i)
    
    # Fetch only missing lineups
    if matches_to_fetch:
        from fetch_team import fetch_and_parse_lineups, get_surname, apply_last3
        from types import SimpleNamespace
        known_surnames = set(get_surname(p["name"]) for p in players if p.get("name"))
        match_objs = [SimpleNamespace(date=m["date"], tournament=m["tournament"], mid=m["mid"], url=m["url"]) for m in matches_to_fetch]
        new_lineups = await fetch_and_parse_lineups(match_objs, known_surnames)
        
        # Save new lineups to cache
        for m, ld in zip(matches_to_fetch, new_lineups):
            mid = m.get("mid", "")
            if mid and ld.get("starters"):
                cache_file = f"{lineups_cache_dir}/{team_id}_{mid}.json"
                ld["_cached_at"] = time.time()
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(ld, f, ensure_ascii=False, indent=2)
                print(f"    {m['date']}: cached lineups ({len(ld.get('starters',[]))} starters)")
        
        # Merge cached and new lineups
        all_lineups = [None] * len(matches)
        for idx, ld in cached_lineups:
            all_lineups[idx] = ld
        for idx, ld in zip(matches_to_fetch_indices, new_lineups):
            all_lineups[idx] = ld
        lineups_data_all = all_lineups
    else:
        # All from cache
        lineups_data_all = [ld for _, ld in sorted(cached_lineups, key=lambda x: x[0])]
    
    valid_pairs = [(m, ld) for m, ld in zip(matches, lineups_data_all) if ld and len(ld.get("starters", [])) > 0]
    if len(valid_pairs) < 3: raise RuntimeError(f"only {len(valid_pairs)} lineups; need >=3")
    matches = [m for m, _ in valid_pairs[:3]]
    lineups_data = [ld for _, ld in valid_pairs[:3]]
    print(f"  lineups in {time.time()-t3:.2f}s")

    print(f"[5/5] Applying last3...")
    players = apply_last3(players, lineups_data)
    m1s = sum(1 for p in players if p.get("last3", [])[0:1] == ["START"])
    m2s = sum(1 for p in players if len(p.get("last3", [])) > 1 and p["last3"][1] == "START")
    m3s = sum(1 for p in players if len(p.get("last3", [])) > 2 and p["last3"][2] == "START")
    if any(c == 0 for c in [m1s, m2s, m3s]) or any(c > 11 for c in [m1s, m2s, m3s]):
        raise RuntimeError(f"invalid START counts={[m1s, m2s, m3s]}")
    print(f"  START: m1={m1s} m2={m2s} m3={m3s}")

    cache["players"] = players
    cache["matches"] = [{"date": m["date"], "tournament": m["tournament"], "url": m["url"], "mid": m["mid"],
                         "score": m.get("score", "") or ld.get("score", ""),
                         "home_team": m.get("home_team", "") or ld.get("home_team", ""),
                         "away_team": m.get("away_team", "") or ld.get("away_team", "")} for m, ld in zip(matches, lineups_data)]
    cache["_cached_at"] = time.time(); cache["last_updated"] = time.time()
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total = time.time() - t0
    print(f"\nDONE in {total:.1f}s - {len(players)} players, {len(cache['matches'])} matches")
    for m in cache["matches"]: print(f"  {m['date']} {m['tournament']}: {m.get('score','?')}")
    return cache

def main():
    if len(sys.argv) < 4:
        print("usage: parse_team_fast.py TEAM_ID TEAM_NAME TEAM_SLUG [--coach-nat NAT] [--stadium STADIUM]")
        sys.exit(1)
    team_id, team_name, team_slug = sys.argv[1], sys.argv[2], sys.argv[3]
    coach_nat = ""; stadium = ""
    args = sys.argv[4:]; i = 0
    while i < len(args):
        a = args[i]
        if a == "--coach-nat" and i + 1 < len(args): coach_nat = args[i+1]; i += 2
        elif a == "--stadium" and i + 1 < len(args): stadium = args[i+1]; i += 2
        else: i += 1
    asyncio.run(fetch_team_fast(team_id, team_name, team_slug, coach_nat, stadium))

if __name__ == "__main__":
    main()
