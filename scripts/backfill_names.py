"""Backfill: clean player.name in cache files AND SQLite is_current=1 rows.

Why this is needed: app.py:prepare_team_data_version() rewrites the cache
file from the SQLite row on every page load. If the SQLite row is dirty,
the file gets dirtied back. The only way to fully fix the issue is to
clean BOTH the file and the DB.

This is v3 — uses _strip_missing_reason_suffix as the source of truth
(prevents false-positive stripping of real surnames like "Van Neck").
"""
import json, os, sys, sqlite3

sys.path.insert(0, '/home/openclaw/FormAlert')
sys.path.insert(0, '/home/openclaw/FormAlert/scripts')
import phase2_generic as p2g
import api_refresh as ar


def clean_one_players_list(players):
    """Return (changed_count, fixed_pairs) — runs strip on each player.name."""
    changed = 0
    pairs = []
    for p in players:
        old = p.get('name', '')
        if not old:
            continue
        new = p2g._strip_missing_reason_suffix(old)
        if new != old:
            p['name'] = new
            changed += 1
            pairs.append((old, new))
    return changed, pairs


def main():
    # Parity check
    sample = "Estêvão Hamstring Injury 01.08.2026"
    p2g_result = p2g._strip_missing_reason_suffix(sample)
    ar_result = ar._strip_missing_reason_suffix(sample)
    if p2g_result != ar_result or p2g_result != "Estêvão":
        sys.exit(f"PARITY ERROR! p2g={p2g_result!r} ar={ar_result!r}")
    print(f"Parity check: PASSED ({sample!r} -> {p2g_result!r} in both modules)")

    cache_dir = '/home/openclaw/.openclaw/workspace'
    db_path = '/home/openclaw/FormAlert/formalert.db'
    files = sorted(
        f for f in os.listdir(cache_dir)
        if f.startswith('_live_cache_') and f.endswith('.json')
    )
    print(f"Found {len(files)} cache files to scan")

    con = sqlite3.connect(db_path)

    file_changed = file_unchanged = file_empty = errors = 0
    db_updated = db_skipped_no_current = 0
    fixed_examples = []

    # ===== Pass 1: clean all cache files =====
    for fn in files:
        team_id = fn.replace('_live_cache_', '').replace('.json', '')
        fp = os.path.join(cache_dir, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        players = d.get('players', [])
        if not players:
            file_empty += 1
            continue

        ch, pairs = clean_one_players_list(players)
        if ch > 0:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            file_changed += 1
            for old, new in pairs[:3]:
                if len(fixed_examples) < 20:
                    fixed_examples.append((fn, old, new))
        else:
            file_unchanged += 1

    # ===== Pass 2: clean all SQLite is_current=1 rows =====
    rows = con.execute(
        "SELECT team_id, data_json FROM team_data_versions WHERE is_current=1"
    ).fetchall()
    print(f"Found {len(rows)} SQLite is_current=1 rows to clean")

    for tid, data_json in rows:
        try:
            d = json.loads(data_json)
        except Exception:
            continue
        players = d.get('players', [])
        if not players:
            continue
        ch, pairs = clean_one_players_list(players)
        if ch > 0:
            new_json = json.dumps(d, ensure_ascii=False)
            con.execute(
                "UPDATE team_data_versions SET data_json=? "
                "WHERE team_id=? AND is_current=1",
                (new_json, tid)
            )
            db_updated += 1
            for old, new in pairs[:3]:
                if len(fixed_examples) < 40:
                    fixed_examples.append((f"DB:{tid}", old, new))

    con.commit()
    con.close()

    print(f"\nResults:")
    print(f"  Files changed:        {file_changed}")
    print(f"  Files unchanged:      {file_unchanged}")
    print(f"  Files empty:          {file_empty}")
    print(f"  Files errors:         {errors}")
    print(f"  DB rows updated:      {db_updated}")
    print(f"\nFirst 20 fixes:")
    for fn, old, new in fixed_examples[:20]:
        print(f"  {fn:50s} | {old!r:50s} -> {new!r}")


if __name__ == '__main__':
    main()
