"""
Per-tournament player stats for the Tournament dropdown.

Aug 20 2026 — Aug 21 2026.
Source: /api/flashscore/v2/teams/squad (the same endpoint
api_refresh.refresh_squad uses for the Total tab), but instead of
returning ONLY the "Total" group, this module walks ALL tab_name groups
(Allsvenskan / Europa League / Conference League / Total) and produces a
flat dict:

    {
      "tabs": [{"key": "Allsvenskan", "label": "Allsvenskan"},
               {"key": "Europa League", "label": "Europa League"},
               ...],
      "players": {
        "Hahn Warner": {
          "Allsvenskan":      {"apps": "17", "minutes": "1530", ...},
          "Europa League":    {"apps":  "2", "minutes":  "180", ...},
          "Conference League":{"apps":  "2", "minutes":  "180", ...},
          "Total":            {"apps": "21", "minutes": "1890", ...}
        },
        ...
      }
    }

API-only — no HTML scraping. Flashscore's /teams/squad already returns
per-tournament data; the existing refresh_squad just filters to Total.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

HOST = "flashscore4.p.rapidapi.com"
HEADERS = {
    "X-Rapidapi-Key": "82f1fc4f2emsh6f172ea91bb5386p1cd344jsndd0fc401e69f",
    "X-Rapidapi-Host": HOST,
    "User-Agent": "curl/8.5.0",
    "Accept": "*/*",
}

CACHE_DIR = "/home/openclaw/.openclaw/workspace"


# Aug 21 2026 — strip Flashscore's trailing injury reason so per-tournament
# player keys match the clean "Surname Name" we get from /teams/squad.
# Real example from lzqk4S68 (AIK, Stockholm):
#   "Wilson Omondi Stanley Groin Injury"  → "Wilson Omondi Stanley"
# Without this the dropdown can't find Stanley under either the DOM swap
# ("Omondi Stanley Wilson") or the raw DOM name ("Stanley Wilson Omondi").
_INJURY_TOKENS = {
    "injury", "injured", "knock", "muscle", "muscles", "hamstring",
    "achilles", "tendon", "ligament", "knee", "ankle", "thigh",
    "calf", "foot", "feet", "toe", "back", "shoulder", "groin",
    "broken", "fracture", "strain", "sprain", "rupture", "tear",
    "suspension", "suspended", "ban", "red", "yellow", "card",
    "covid", "covid-19", "ill", "illness", "sick", "fever",
    "rest", "rested", "personal", "family", "birth", "private",
}


# Aug 21 2026 — mirrors api_refresh._date_pattern() but inline so we
# don't have to import the heavy refresh module.
_DATE_PATTERN = __import__("re").compile(
    r"\s+\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\s*$"
)


def _strip_injury_suffix(name):
    """Drop trailing injury/reason tokens and date from a player name.

    Aug 21 2026 — see AIK + IP5zl0cJ + IXVkvT2D + jNvak2f3 real data:
      "Wilson Omondi Stanley Groin Injury"          → "Wilson Omondi Stanley"
      "Egiluz Unai Knee Injury 15.02.2027"          → "Egiluz Unai"
      "Zorin Daniil Achilles Tendon Injury 04.01.2027" → "Zorin Daniil"
      "Odriozola Alvaro Knee Injury 02.11.2026"     → "Odriozola Alvaro"

    Algorithm:
      1. Strip any trailing date first (e.g. " 15.02.2027").
      2. While the last token is an injury/reason word, drop it.
      3. If everything got stripped (e.g. name was just a reason), return
         the original so we never lose the player.
    """
    if not name:
        return name
    original = str(name).strip()
    name = _DATE_PATTERN.sub("", original).strip()
    parts = name.split()
    while len(parts) > 1 and parts[-1].lower().rstrip(",.") in _INJURY_TOKENS:
        parts.pop()
    cleaned = " ".join(parts).strip()
    return cleaned if cleaned else original


CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h


def _cache_path(team_id: str) -> str:
    return os.path.join(CACHE_DIR, f"_per_tournament_{team_id}.json")


def _read_cache(team_id: str):
    path = _cache_path(team_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(team_id: str, data: dict) -> None:
    path = _cache_path(team_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _is_fresh(team_id: str) -> bool:
    path = _cache_path(team_id)
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < CACHE_TTL_SECONDS


def _fetch_squad(team_id: str, slug: str):
    """Hit the Flashscore squad endpoint. Returns the raw list (or None)."""
    url = f"https://{HOST}/api/flashscore/v2/teams/squad?team_url=%2Fteam%2F{urllib.parse.quote(slug, safe='')}%2F{team_id}%2F"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[per_tournament] fetch error for {team_id}: {e}")
        return None


def _build_per_tournament(raw_groups):
    """Convert the raw list of 4 groups into the {tabs, players} dict."""
    tabs = []
    players = {}

    if not isinstance(raw_groups, list):
        return {"tabs": tabs, "players": players}

    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        tab_name = (group.get("tab_name") or "").strip()
        if not tab_name:
            continue
        tabs.append({"key": tab_name, "label": tab_name})
        for section in group.get("list", []) or []:
            if not isinstance(section, dict):
                continue
            if (section.get("name") or "").strip().lower() == "coach":
                continue
            for p in section.get("players", []) or []:
                if not isinstance(p, dict):
                    continue
                name = (p.get("name") or "").strip()
                name = _strip_injury_suffix(name)
                if not name:
                    continue
                # Flashscore format: "Surname Name" (e.g. "Hahn Warner").
                # The DOM row shows "Name Surname" (e.g. "Warner Hahn").
                # The JS side swaps "Hahn Warner" → "Warner Hahn" before
                # matching; we keep API names verbatim here so the JS can
                # do a single canonical lookup.
                if name not in players:
                    players[name] = {}
                players[name][tab_name] = {
                    "apps": p.get("matches_played", "") or "",
                    "minutes": p.get("minutes_played", "") or "",
                    "goals": p.get("goals_scored", "") or "",
                    "assists": p.get("assists", "") or "",
                    "yellow": p.get("yellow_cards", "") or "",
                    "red": p.get("red_cards", "") or "",
                }

    return {"tabs": tabs, "players": players}


def get_per_tournament(team_id: str, slug: str, force: bool = False) -> dict:
    """Return per-tournament data for a team.

    Reads from cache when fresh. On miss/stale, hits the squad API and
    stores the parsed dict for CACHE_TTL_SECONDS.
    """
    if not force and _is_fresh(team_id):
        cached = _read_cache(team_id)
        if cached and cached.get("players"):
            return cached

    raw = _fetch_squad(team_id, slug)
    if raw is None:
        # Last-resort: stale cache is better than nothing
        cached = _read_cache(team_id)
        if cached:
            return cached
        return {"tabs": [], "players": {}, "team_id": team_id, "error": "fetch_failed"}
    if raw == []:
        # Empty list = API says "no data for this team". Still cache so we
        # don't hammer the API on every page load.
        empty = {"tabs": [], "players": {}, "team_id": team_id, "empty": True}
        _write_cache(team_id, empty)
        return empty

    parsed = _build_per_tournament(raw)
    parsed["team_id"] = team_id
    _write_cache(team_id, parsed)
    return parsed