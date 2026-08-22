"""
Spain LaLiga fixtures aggregator — feeds the 🔮 Predicted XI header button.

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

The /teams/fixtures payload does NOT carry round information — for
that we additionally hit /matches/details per unique match_id, which
returns `tournament.name` like "LaLiga - Round 2". The round value
for each match is cached on disk in
/home/openclaw/.openclaw/workspace/_match_round_cache.json so we
don't hit the API for the same match repeatedly. Round lookups for
matches not yet in the cache happen on a daemon thread so the
user-facing response returns in <2s; the panel reloads the round
labels on the next visit (24h TTL on the assembled fixtures cache).

API-only — no HTML scraping, no Soccerway.
"""
from __future__ import annotations

import json
import os
import re
import threading
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
FIXTURES_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h for assembled payload
ROUND_CACHE_FILE = os.path.join(CACHE_DIR, "_match_round_cache.json")
# Aug 21 2026 — bumped from 10 to 30 to cover 2-3 future rounds (10
# matches per LaLiga round × ~3 rounds).
MAX_FIXTURES_RETURN = 30


# ---------------------------------------------------------------------------
# Cache helpers — assembled fixtures (24h TTL)
# ---------------------------------------------------------------------------
def _fixtures_cache_path():
    return os.path.join(CACHE_DIR, "_laliga_fixtures.json")


def _read_fixtures_cache():
    path = _fixtures_cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_fixtures_cache(data: dict) -> None:
    path = _fixtures_cache_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _is_fresh() -> bool:
    path = _fixtures_cache_path()
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < FIXTURES_CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Round lookup cache (persistent, no TTL — match_id never re-assigned)
# ---------------------------------------------------------------------------
def _read_round_cache() -> dict:
    if not os.path.exists(ROUND_CACHE_FILE):
        return {}
    try:
        with open(ROUND_CACHE_FILE) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_round_cache(cache: dict) -> None:
    tmp = ROUND_CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, ROUND_CACHE_FILE)


def _parse_round_label(name: str) -> str:
    """Extract a sortable round label from "LaLiga - Round 2" etc.

    Aug 21 2026 — Flashscore's tournament.name for match details is a
    free-form string. Common patterns seen in production:
        "LaLiga - Round 2"
        "LaLiga - Round 22"
        "LaLiga2 - Round 1"   (Segunda)
        "LaLiga - Play Offs"  (when the season has them)
    We pull the numeric token out so the JS layer can sort rounds
    chronologically.
    """
    if not name:
        return ""
    m = re.search(r"[Rr]ound\s+(\d+)", name)
    if m:
        return "Round " + m.group(1)
    return name.strip()


# ---------------------------------------------------------------------------
# LaLiga team ids
# ---------------------------------------------------------------------------
def _load_laliga_team_ids():
    """Read LaLiga + LaLiga 2 team ids from leagues_data.json.

    Aug 22 2026 — Predicted XI panel was only fed LaLiga 1. LaLiga 2
    (Segunda Division) shares the same Predicted XI panel header so
    we pull both tournaments' team ids from leagues_data.json. The
    /teams/fixtures endpoint is per-team anyway, so the cost is just
    one extra round of network calls — fixtures are deduped later by
    match_id.
    """
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
        ids = []
        # Aug 22 2026 — leagues_data.json uses the literal key "LaLiga2"
        # (no space) for Segunda División. We accept both spellings so
        # a future rename doesn't break this loader.
        for tournament_key in ("LaLiga", "LaLiga 2", "LaLiga2"):
            teams = spain.get(tournament_key) or []
            ids.extend(t.get("id") for t in teams if t.get("id"))
        return ids
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
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


def _fetch_match_details(match_id: str):
    """Hit /matches/details for one match. Returns parsed dict (or None)."""
    url = f"https://{HOST}/api/flashscore/v2/matches/details?match_id={match_id}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[laliga_fixtures] match details error for {match_id}: {e}")
        return None


def _laliga_matches_from_team_response(team_id: str, raw):
    """Pull just the LaLiga matches from a /teams/fixtures response."""
    if not isinstance(raw, list):
        return []
    out = []
    for tournament in raw:
        if not isinstance(tournament, dict):
            continue
        name = (tournament.get("name") or "").strip()
        country = (tournament.get("country_name") or "").strip().lower()
        url = (tournament.get("tournament_url") or "").strip()
        is_laliga = (
            (name == "LaLiga" and country == "spain")
            or ("/spain/laliga/" in url.lower())
            # Aug 22 2026 — LaLiga 2 (Segunda División). Flashscore
            # labels it "LaLiga 2" with country Spain, and the url is
            # /football/spain/laliga-2/. We treat it as a sibling
            # tournament so the Predicted XI panel can show its
            # fixtures and the cache hydration loop can run for it.
            or (name == "LaLiga 2" and country == "spain")
            or ("/spain/laliga-2/" in url.lower())
            or ("/spain/laliga2/" in url.lower())
        )
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
            # Aug 22 2026 — carry the division name so the JS panel
            # can group fixtures into separate LaLiga / LaLiga 2
            # dropdowns instead of lumping them under one selector.
            # Use "LaLiga 2" for Segunda Division fixtures (matches
            # the panel header we'd write in lineup_team_view.py),
            # and the short "LaLiga" for everything else that
            # matched the is_laliga test above.
            division = "LaLiga 2" if (name == "LaLiga 2"
                                       or "/laliga-2/" in url.lower()
                                       or "/laliga2/" in url.lower()) else "LaLiga"
            out.append({
                "match_id": m.get("match_id"),
                "timestamp": ts,
                "tournament": division,
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


def _resolve_round(match_id: str, round_cache: dict) -> str:
    """Look up (or fetch) the round label for one match_id."""
    if not match_id:
        return ""
    if match_id in round_cache and round_cache[match_id]:
        return round_cache[match_id]
    details = _fetch_match_details(match_id)
    if not details:
        # Cache the empty string too so we don't hammer the API if
        # the endpoint is temporarily flaky.
        round_cache[match_id] = ""
        return ""
    tournament = (details.get("tournament") or {})
    label = _parse_round_label(tournament.get("name") or "")
    round_cache[match_id] = label
    return label


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def get_laliga_fixtures(force: bool = False) -> dict:
    """Return up to MAX_FIXTURES_RETURN upcoming LaLiga matches, each
    with a `round` field attached (when known).

    Aug 21 2026 — restructured for speed. Previously we did up to 30
    sequential /matches/details calls inside the request handler, which
    could take >60s and time out. Now:
      1) If the on-disk fixtures cache is fresh (24h), return it
         immediately. No network calls.
      2) Otherwise assemble the aggregated fixtures list (20 teams × 1
         /teams/fixtures call each, ~1-2s), persist that list to disk
         with whatever rounds we already have from the round cache,
         and return it within a second. Missing rounds are filled as
         empty strings.
      3) A separate background helper fills in missing rounds over
         time and rewrites the on-disk fixtures cache.
    """
    if not force and _is_fresh():
        cached = _read_fixtures_cache()
        if cached and cached.get("fixtures"):
            return cached

    team_ids = _load_laliga_team_ids()
    if not team_ids:
        cached = _read_fixtures_cache()
        if cached:
            return cached
        return {
            "fixtures": [],
            "team_count": 0,
            "error": "leagues_data.json missing or unreadable",
        }

    # 1) Aggregate from /teams/fixtures for each LaLiga team.
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

    aggregated.sort(key=lambda x: x.get("timestamp") or 0)

    # 2) Stamp known rounds from disk cache immediately; leave unknown
    #    ones with empty string for now.
    round_cache = _read_round_cache()
    for m in aggregated:
        mid = m.get("match_id")
        m["round"] = round_cache.get(mid, "") if mid else ""

    trimmed = aggregated[:MAX_FIXTURES_RETURN]

    payload = {
        "fixtures": trimmed,
        "team_count": len(team_ids),
        "fetched_at": time.time(),
    }
    _write_fixtures_cache(payload)

    # 3) Kick off background round resolution for matches we still
    #    don't know. Returns instantly; the user-facing response is
    #    already on its way back to the browser.
    threading.Thread(
        target=_background_resolve_rounds,
        args=(trimmed,),
        daemon=True,
    ).start()

    return payload


def _background_resolve_rounds(fixtures: list) -> None:
    """Fill in the round field for matches missing it.

    Aug 21 2026 — runs on a daemon thread so it doesn't block the
    FastAPI response. Walks the fixtures list, fetches /matches/details
    for the ones still missing a round, updates the on-disk round
    cache and the on-disk fixtures cache, then exits.
    """
    try:
        round_cache = _read_round_cache()
        updated = False
        for m in fixtures:
            mid = m.get("match_id")
            if not mid:
                continue
            if mid in round_cache and round_cache[mid]:
                continue
            label = _resolve_round(mid, round_cache)
            if label:
                m["round"] = label
                updated = True
            # Tiny sleep to be polite to the upstream API.
            time.sleep(0.05)
        if updated:
            _write_round_cache(round_cache)
            # Refresh the fixtures cache with the round labels.
            cached = _read_fixtures_cache() or {}
            cached_fixtures = cached.get("fixtures") or []
            label_by_id = {x.get("match_id"): x.get("round", "") for x in fixtures}
            for cf in cached_fixtures:
                mid = cf.get("match_id")
                if mid in label_by_id and not cf.get("round"):
                    cf["round"] = label_by_id[mid]
                    updated = True
            if updated:
                _write_fixtures_cache(cached)
    except Exception as e:
        print(f"[laliga_fixtures] background resolve error: {e}")
