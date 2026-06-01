#!/usr/bin/env python3
"""Safely prefill FormAlert team cache for one league.

Usage:
  python3 prefill_league_cache.py "England" "Premier League"

Runs teams sequentially so Soccerway/Playwright does not overload the VPS.
For each team: full fetch -> save current DB version.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python3")
CACHE_DIR = "/home/openclaw/.openclaw/workspace"

sys.path.insert(0, ROOT)
import app  # noqa: E402


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def main() -> int:
    if len(sys.argv) < 3:
        print('Usage: python3 prefill_league_cache.py "Country" "League"')
        return 2
    country, league = sys.argv[1], sys.argv[2]
    with open(os.path.join(ROOT, "leagues_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    teams = data.get(country, {}).get(league, [])
    if not teams:
        log(f"No teams for {country}/{league}")
        return 1
    ok = []
    failed = []
    for idx, team in enumerate(teams, 1):
        tid = str(team.get("id") or "")
        name = str(team.get("name") or tid)
        slug = str(team.get("slug") or "")
        stadium = str(team.get("stadium") or "")
        coach_nat = str(team.get("coach_nationality") or "")
        if not tid:
            failed.append((name, "missing id"))
            continue
        log(f"START {idx}/{len(teams)} {name} {tid} slug={slug}")
        cache_path = os.path.join(CACHE_DIR, f"_live_cache_{tid}.json")
        try:
            cmd = [VENV_PY, "-u", os.path.join(ROOT, "fetch_team.py"), tid, "--full", "--team-name", name]
            if slug:
                cmd += ["--slug", slug]
            if coach_nat:
                cmd += ["--coach-nat", coach_nat]
            if stadium:
                cmd += ["--stadium", stadium]
            proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=900)
            tail = (proc.stdout + proc.stderr)[-3000:]
            if proc.returncode != 0:
                raise RuntimeError(f"fetch rc={proc.returncode}\n{tail}")
            fresh = app._read_team_cache(tid)
            players = len(fresh.get("players") or [])
            matches = len(fresh.get("matches") or [])
            if players <= 0:
                raise RuntimeError(f"empty players after fetch\n{tail}")
            saved = app._save_team_version(tid, fresh)
            log(f"OK {name}: players={players} matches={matches} save={saved}")
            ok.append((name, players, matches))
        except Exception as exc:
            log(f"FAIL {name}: {exc}")
            failed.append((name, str(exc)[-800:]))
        time.sleep(3)
    log(f"SUMMARY ok={len(ok)} failed={len(failed)}")
    for item in ok:
        log(f"OK_ITEM {item[0]} players={item[1]} matches={item[2]}")
    for item in failed:
        log(f"FAILED_ITEM {item[0]} reason={item[1]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
