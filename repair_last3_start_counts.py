#!/usr/bin/env python3
"""Repair existing FormAlert caches where Last 3 START count is > 11.

Rule: per team per match, at most 11 START players. Soccerway lineup entries are
matched to roster players one-to-one using surname + initials. If the original
lineup data is not available (existing cache only has player last3), this script
repairs over-counted matches by demoting the weakest duplicate-family excess
STARTs to '-' until START count <= 11. It prioritizes keeping players with:
  1) higher season minutes,
  2) higher apps,
  3) higher impact_score,
  4) lower roster order.
This is deterministic and fixes the known duplicate-surname/ambiguous-name bug
without fabricating starts for unavailable reserve players.
"""
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = "/home/openclaw/.openclaw/workspace" if os.path.isdir("/home/openclaw/.openclaw/workspace") else os.path.join(ROOT, "cache")
sys.path.insert(0, ROOT)
try:
    import app
except Exception:
    app = None


def surname(name):
    parts = str(name or "").strip().split()
    return parts[0].lower().rstrip('.').replace('.', '') if parts else ""


def num(v):
    try:
        return float(str(v or 0).replace(',', '').replace('€', '').replace('m', '').replace('bn', ''))
    except Exception:
        return 0.0


def keep_score(player, idx):
    return (
        num(player.get('min')),
        num(player.get('apps')),
        num(player.get('impact_score')),
        -idx,
    )


def repair_file(path):
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception as exc:
        return [], f"load_error {exc}"
    players = data.get('players') or []
    if not players:
        return [], None
    changes = []
    for mi in range(3):
        starters = [(idx, p) for idx, p in enumerate(players) if len(p.get('last3', [])) > mi and p.get('last3', [])[mi] == 'START']
        if len(starters) <= 11:
            continue
        excess = len(starters) - 11
        # First target duplicate surname/first-token families, because this is the
        # bug source. If still >11, demote weakest remaining starts.
        demote = []
        by_surname = {}
        for idx, p in starters:
            by_surname.setdefault(surname(p.get('name')), []).append((idx, p))
        for fam in by_surname.values():
            if len(fam) <= 1:
                continue
            ranked = sorted(fam, key=lambda ip: keep_score(ip[1], ip[0]), reverse=True)
            demote.extend(ranked[1:])
        if len(demote) < excess:
            already = {id(p) for _, p in demote}
            remaining = [(idx, p) for idx, p in starters if id(p) not in already]
            demote.extend(sorted(remaining, key=lambda ip: keep_score(ip[1], ip[0]))[:excess-len(demote)])
        demote = sorted(demote, key=lambda ip: keep_score(ip[1], ip[0]))[:excess]
        for idx, p in demote:
            p['last3'][mi] = '-'
            if len(p.get('last3_captain', [])) > mi:
                p['last3_captain'][mi] = False
            if len(p.get('last3_missing', [])) > mi:
                p['last3_missing'][mi] = None
            changes.append({
                'match_index': mi,
                'player': p.get('name'),
                'reason': 'demoted_duplicate_or_excess_start',
            })
    if changes:
        data['last_updated'] = __import__('time').time()
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        tid = os.path.basename(path)[12:-5]
        if app and hasattr(app, '_save_team_version'):
            try:
                app._save_team_version(tid, data)
            except Exception as exc:
                changes.append({'version_error': str(exc)})
    return changes, None


def main():
    total_files = 0
    fixed_files = 0
    total_changes = 0
    for path in sorted(glob.glob(os.path.join(CACHE_DIR, '_live_cache_*.json'))):
        total_files += 1
        changes, err = repair_file(path)
        if err:
            print('ERROR', path, err)
            continue
        if changes:
            fixed_files += 1
            total_changes += len([c for c in changes if 'player' in c])
            tid = os.path.basename(path)[12:-5]
            data = json.load(open(path, encoding='utf-8'))
            team = data.get('team', {}).get('name', tid)
            print('FIXED', team, tid, 'changes', changes)
    print('DONE', 'files', total_files, 'fixed_files', fixed_files, 'player_changes', total_changes)


if __name__ == '__main__':
    main()
