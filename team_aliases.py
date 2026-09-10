"""
team_aliases.py — Universal team-name mapping layer (Sep 10 2026).

Resolves rotowire/external name -> LV team_id via explicit aliases,
falling back to _name_eq + _match_score fuzzy match in rotowire_fixtures.py.

Storage: data/team_name_aliases.json (JSON, atomic write via tmp+rename).
Schema:
{
  "<lv_team_id>": {
    "name": "Bodo/Glimt",                    # LV canonical name (read from leagues_data.json)
    "league": "Norway > Eliteserien",        # LV league path
    "aliases": ["Bodo/Glimt", "Glimt", "FK Bodø/Glimt"],
    "rotowire_seen": ["Glimt"]               # auto-learned rotowire names
  }
}

The alias-lookup is THE FIRST gate before any fuzzy matching, so:
- Bodo/Glimt -> Glimt (alias list) -> 100% deterministic
- Man Utd -> Manchester United (alias list) -> 100% deterministic
- Future rotowire name changes only need one aliases.json update
"""
from __future__ import annotations
import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Optional

# Default storage location (relative to project root).
DATA_DIR = Path(os.environ.get("FORMALERT_DATA_DIR", "/home/openclaw/FormAlert/data"))
ALIASES_PATH = DATA_DIR / "team_name_aliases.json"

_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_mtime: float = 0.0


def _strip(s: str) -> str:
    """NFD + lowercase + trim — matches rotowire_fixtures._name_eq/_match_score."""
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn").strip()


def _norm(s: str) -> str:
    """Normalization used as the alias dict key: stripped + collapsed whitespace."""
    n = _strip(s)
    return re.sub(r"\s+", " ", n)


def _load_if_stale() -> dict:
    """Read JSON from disk, reload if mtime changed. Thread-safe."""
    global _cache, _cache_mtime
    with _lock:
        if not ALIASES_PATH.exists():
            _cache = {}
            _cache_mtime = 0.0
            return _cache
        mtime = ALIASES_PATH.stat().st_mtime
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        try:
            with ALIASES_PATH.open("r", encoding="utf-8") as f:
                _cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            _cache = {}
        _cache_mtime = mtime
        return _cache


def _save(data: dict) -> None:
    """Atomic save: write tmp + os.replace. Thread-safe."""
    global _cache, _cache_mtime
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ALIASES_PATH.with_suffix(".json.tmp")
    with _lock:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, ALIASES_PATH)
        _cache = data
        _cache_mtime = ALIASES_PATH.stat().st_mtime


def _build_index(data: dict) -> dict[str, str]:
    """Build {normalized_name_or_alias: lv_team_id} index from aliases data.

    Includes canonical name + every alias + every rotowire_seen value.
    First-match wins (insertion order)."""
    idx: dict[str, str] = {}
    for team_id, entry in data.items():
        names = []
        if entry.get("name"):
            names.append(entry["name"])
        names.extend(entry.get("aliases") or [])
        names.extend(entry.get("rotowire_seen") or [])
        for n in names:
            k = _norm(n)
            if k and k not in idx:
                idx[k] = team_id
    return idx


def resolve(external_name: str) -> Optional[str]:
    """Return LV team_id for an external name, or None if not in aliases.

    Lookup is exact-normalized — no fuzzy logic. Fuzzy fallback is done
    by the caller (find_lv_team in app.py)."""
    data = _load_if_stale()
    idx = _build_index(data)
    return idx.get(_norm(external_name))


def resolve_with_meta(external_name: str) -> Optional[dict]:
    """Like resolve() but returns the full entry {id, name, league, matched_via}."""
    team_id = resolve(external_name)
    if not team_id:
        return None
    data = _load_if_stale()
    entry = data.get(team_id, {})
    return {
        "id": team_id,
        "name": entry.get("name", ""),
        "league": entry.get("league", ""),
        "matched_via": "alias",
    }


def learn_rotowire_name(lv_team_id: str, rotowire_name: str, lv_name: str = "",
                        lv_league: str = "") -> bool:
    """Add rotowire_name to a team's rotowire_seen list (auto-learning).

    Returns True if added, False if already present or invalid. Idempotent.
    Used by find_lv_team to remember successful fuzzy matches so future
    lookups hit the fast alias path."""
    if not lv_team_id or not rotowire_name:
        return False
    data = _load_if_stale()
    entry = data.setdefault(lv_team_id, {
        "name": lv_name,
        "league": lv_league,
        "aliases": [],
        "rotowire_seen": [],
    })
    # Ensure name/league are populated if newly added
    if not entry.get("name") and lv_name:
        entry["name"] = lv_name
    if not entry.get("league") and lv_league:
        entry["league"] = lv_league
    if "aliases" not in entry:
        entry["aliases"] = []
    if "rotowire_seen" not in entry:
        entry["rotowire_seen"] = []
    if rotowire_name in entry["rotowire_seen"]:
        return False
    entry["rotowire_seen"].append(rotowire_name)
    _save(data)
    return True


def add_alias(lv_team_id: str, alias: str, lv_name: str = "", lv_league: str = "",
              category: str = "alias") -> dict:
    """Manually add an alias. category: 'alias' or 'rotowire_seen'.

    Returns the updated entry. Idempotent for the (id, alias, category) triple."""
    if category not in ("alias", "rotowire_seen"):
        raise ValueError(f"category must be 'alias' or 'rotowire_seen', got {category!r}")
    data = _load_if_stale()
    entry = data.setdefault(lv_team_id, {
        "name": lv_name,
        "league": lv_league,
        "aliases": [],
        "rotowire_seen": [],
    })
    if not entry.get("name") and lv_name:
        entry["name"] = lv_name
    if not entry.get("league") and lv_league:
        entry["league"] = lv_league
    bucket = entry.setdefault("aliases" if category == "alias" else "rotowire_seen", [])
    if alias not in bucket:
        bucket.append(alias)
    _save(data)
    return entry


def remove_alias(lv_team_id: str, alias: str, category: str = "alias") -> bool:
    """Remove an alias. Returns True if removed."""
    if category not in ("alias", "rotowire_seen"):
        raise ValueError(f"category must be 'alias' or 'rotowire_seen', got {category!r}")
    data = _load_if_stale()
    entry = data.get(lv_team_id)
    if not entry:
        return False
    bucket = entry.get("aliases" if category == "alias" else "rotowire_seen", [])
    if alias in bucket:
        bucket.remove(alias)
        _save(data)
        return True
    return False


def remove_team(lv_team_id: str) -> bool:
    """Remove a team's entry entirely. Returns True if removed."""
    data = _load_if_stale()
    if lv_team_id in data:
        del data[lv_team_id]
        _save(data)
        return True
    return False


def get_all() -> dict:
    """Return full aliases dict (read-only reference)."""
    return _load_if_stale()


def stats() -> dict:
    """Return summary stats."""
    data = _load_if_stale()
    total_aliases = sum(len(e.get("aliases") or []) for e in data.values())
    total_seen = sum(len(e.get("rotowire_seen") or []) for e in data.values())
    return {
        "teams": len(data),
        "total_aliases": total_aliases,
        "total_rotowire_seen": total_seen,
        "path": str(ALIASES_PATH),
    }


# --- CLI / seed helper ---
def seed_from_leagues(leagues_data_path: str = "/home/openclaw/FormAlert/leagues_data.json",
                      only_country: Optional[str] = None,
                      only_league: Optional[str] = None,
                      dry_run: bool = False) -> dict:
    """Seed entries from leagues_data.json — adds entries for teams that
    don't yet have an aliases entry. Existing entries are NOT overwritten
    (we only set name/league if currently empty)."""
    leagues_path = Path(leagues_data_path)
    leagues = json.loads(leagues_path.read_text())
    data = _load_if_stale()
    added = 0
    updated = 0
    skipped = 0
    for country, l_dict in leagues.items():
        if only_country and country != only_country:
            continue
        for lname, teams in l_dict.items():
            if only_league and lname != only_league:
                continue
            for t in teams:
                tid = t.get("id")
                tname = t.get("name", "")
                if not tid or not tname:
                    skipped += 1
                    continue
                league_path = f"{country} > {lname}"
                if tid in data:
                    entry = data[tid]
                    if not entry.get("name"):
                        entry["name"] = tname
                        updated += 1
                    if not entry.get("league"):
                        entry["league"] = league_path
                        updated += 1
                else:
                    data[tid] = {
                        "name": tname,
                        "league": league_path,
                        "aliases": [],
                        "rotowire_seen": [],
                    }
                    added += 1
    if not dry_run:
        _save(data)
    return {"added": added, "updated": updated, "skipped": skipped,
            "total_in_file": len(data), "dry_run": dry_run}


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "seed":
        only_c = sys.argv[2] if len(sys.argv) > 2 else None
        only_l = sys.argv[3] if len(sys.argv) > 3 else None
        result = seed_from_leagues(only_country=only_c, only_league=only_l)
        print(json.dumps(result, indent=2))
    elif len(sys.argv) >= 2 and sys.argv[1] == "stats":
        print(json.dumps(stats(), indent=2))
    else:
        print("Usage: team_aliases.py {seed [country] [league] | stats}")
