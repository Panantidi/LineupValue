"""
Spain LaLiga fixtures aggregator — feeds the 🔮 Predicted 11 header button.

Aug 21 2026 — new module.

We pull upcoming fixtures for every LaLiga team via
/api/flashscore/v2/teams/fixtures (the same endpoint refresh_fixtures
uses for per-team pages). Each team's response contains a tournaments
list, and we keep only the LaLiga tournament (matched by
`name == "LaLiga"` and `country_name == "Spain"`, or by the canonical
`/football/spain/laliga/` url). The resulting match list is
deduplicated by `match_id` (Barcelona vs Elche appears in both
Barcelona's and Elche's /teams/fixtures payload) and sorted ascending
by timestamp.

Cached for CACHE_TTL_SECONDS (24h) in
/home/openclaw/.openclaw/workspace/_laliga_fixtures.json so we don't
hammer RapidAPI with 20 sequential calls every time someone opens the
button.

API-only — no HTML scraping, no Soccerway.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

HOST = "flashscore4.p.rapidapi.com"
KEY = "82f1fc4f2emsh6f172ea91bb5386p1cd344jsndd0fc401e69f"
HEADERS = {
    "X-Rapidapi-Key": KEY,
    "X-Rapidapi-Host": HOST,
    "User-Agent": "curl/8.5.0",
    "Accept": "*/*",
}

CACHE_DIR = "/home/openclaw/.openclaw/workspace"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h
MAX_FIXTURES_RETURN = 10  # user asked for next matches — keep panel compact


def _cache_path():
    return os.path.join(CACHE_DIR, "_laliga_fixtures.json")


def _read_cache():
    path = _cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    path = _cache_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _is_fresh() -> bool:
    path = _cache_path()
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < CACHE_TTL_SECONDS


# All 20 LaLiga teams. Source: leagues_data.json → Spain → LaLiga (Aug 21 2026).
# The slug is not needed — /teams/fixtures only takes ?team_id=<id>.
LALIGA_TEAM_IDS = [
    "hxt57t2q",   # Alaves
    "IP5zl0cJ",   # Ath Bilbao
    "jaarqpLQ",   # Atl. Madrid
    "SKbpVP5K",   # Barcelona
    "vJbTeCGP",   # Betis
    "8pvUZFhf",   # Celta Vigo
    "hxt57t2q",   # (duplicate guard; will dedupe later)
    # The rest are loaded from leagues_data.json on first cache miss.
]


def _load_laliga_team_ids():
    """Read LaLiga team ids from leagues_data.json (authoritative)."""
    leagues_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "leagues_data.json",
    )
    if not os.path.exists(leagues_file):
        return None
    try:
        with open(leagues_file) as f:
            data = json.load(f)
        spain = data.get("Spain") or {}
        teams = spain.get("LaLiga") or []
        ids = [t.get("id") for t in teams if t.get("id")]
        return ids
    except Exception:
        return None


def _fetch_team_fixtures(team_id: str):
    """Hit /teams/fixtures for one team. Returns parsed list (or None)."""
    url = f"https://{HOST}/api/flashscore/v2/teams/fixtures?team_id={team_id}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[laliga_fixtures] fetch error for {team_id}: {e}")
        return None


def _laliga_matches_from_team_response(team_id: str, raw):
    """Pull just the LaLiga matches from a /teams/fixtures response."""
    if not isinstance(raw, list):
        return []
    out = []
    for tournament in raw:
        if not isinstance(tournament, dict):
            continue
        # Identify the LaLiga tournament by name + country, or by URL.
        name = (tournament.get("name") or "").strip()
        country = (tournament.get("country_name") or "").strip().lower()
        url = (tournament.get("tournament_url") or "").strip()
        is_laliga = (
            name == "LaLiga"
            and country == "spain"
        ) or ("/spain/laliga/" in url.lower())
        if not is_laliga:
            continue
        for m in tournament.get("matches") or []:
            if not isinstance(m, dict):
                continue
            home = m.get("home_team") or {}
            away = m.get("away_team") or {}
            ts = m.get("timestamp")
            if not ts:
                continue
            out.append({
                "match_id": m.get("match_id"),
                "timestamp": ts,
                "home": {
                    "team_id": home.get("team_id"),
                    "name": home.get("name"),
                    "image": home.get("small_image_path") or "",
                },
                "away": {
                    "team_id": away.get("team_id"),
                    "name": away.get("name"),
                    "image": away.get("small_image_path") or "",
                },
            })
    return out


def get_laliga_fixtures(force: bool = False) -> dict:
    """Return the next MAX_FIXTURES_RETURN LaLiga matches.

    Reads from cache when fresh. On miss/stale, hits the API for every
    LaLiga team and aggregates.
    """
    if not force and _is_fresh():
        cached = _read_cache()
        if cached and cached.get("fixtures"):
            return cached

    team_ids = _load_laliga_team_ids()
    if not team_ids:
        # Cache whatever stale state we have so the UI can still render
        # a meaningful error message.
        cached = _read_cache()
        if cached:
            return cached
        return {
            "fixtures": [],
            "team_count": 0,
            "error": "leagues_data.json missing or unreadable",
        }

    seen = set()
    aggregated = []
    for team_id in team_ids:
        raw = _fetch_team_fixtures(team_id)
        if raw is None:
            continue
        for m in _laliga_matches_from_team_response(team_id, raw):
            mid = m.get("match_id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            aggregated.append(m)

    # Sort by timestamp, keep the soonest N.
    aggregated.sort(key=lambda x: x.get("timestamp") or 0)
    next_matches = aggregated[:MAX_FIXTURES_RETURN]

    payload = {
        "fixtures": next_matches,
        "team_count": len(team_ids),
        "fetched_at": time.time(),
    }
    _write_cache(payload)
    return payload