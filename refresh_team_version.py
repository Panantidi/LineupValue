#!/usr/bin/env python3
"""Background updater for FormAlert team data versions.

Never called in the request path directly. It serializes per team via /tmp lock,
fetches fresh data, compares canonical fields using app.py helpers, and only
creates a new DB version when data changed.
"""
import os
import re
import sys
import time
import traceback

TEAM_ID = sys.argv[1] if len(sys.argv) > 1 else ""
if not TEAM_ID:
    raise SystemExit("usage: refresh_team_version.py TEAM_ID")

LOCK = os.path.join("/tmp", f"formalert_refresh_{re.sub(r'[^A-Za-z0-9_.-]', '_', TEAM_ID)}.lock")
GLOBAL_LOCK = os.path.join("/tmp", "formalert_refresh_global.lock")
LOG = os.path.join("/tmp", f"formalert_refresh_{re.sub(r'[^A-Za-z0-9_.-]', '_', TEAM_ID)}.log")


def acquire_lock(path: str) -> bool:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(path) > 1800:
                os.remove(path)
                return acquire_lock(path)
        except Exception:
            pass
        return False


# Atomic locks. Only one Soccerway/Playwright refresh may run globally.
if not acquire_lock(GLOBAL_LOCK):
    raise SystemExit(0)
if not acquire_lock(LOCK):
    try:
        os.remove(GLOBAL_LOCK)
    except FileNotFoundError:
        pass
    raise SystemExit(0)

try:
    sys.path.insert(0, os.path.dirname(__file__))
    import app

    current = app._get_current_team_version(TEAM_ID)
    base = current["data"] if current else None
    fresh = app._fetch_fresh_team_data(TEAM_ID, base)
    if fresh and fresh.get("players"):
        result = app._save_team_version(TEAM_ID, fresh)
        app._write_team_cache(TEAM_ID, fresh)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ok {TEAM_ID} {result}\n")
except Exception:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} error {TEAM_ID}\n")
        f.write(traceback.format_exc()[-4000:] + "\n")
finally:
    for path in (LOCK, GLOBAL_LOCK):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
