#!/usr/bin/env python3
"""Backfill last3_missing for injured players in existing caches."""
import sys
# Make sure /tmp is NOT first in sys.path (avoid shadowing 'inspect' module)
sys.path = [p for p in sys.path if p not in ("", "/tmp", ".")]
import asyncio, json, os, re, time
import httpx
from bs4 import BeautifulSoup

CACHE_DIR = "/home/openclaw/.openclaw/workspace"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.5",
}
BASE = "https://www.soccerway.com"

def get_squad_html(team_id, team_slug):
    url = f"{BASE}/team/{team_slug}/{team_id}/squad/"
    r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    r.raise_for_status()
    return r.text

def parse_injuries(html):
    soup = BeautifulSoup(html, "html.parser")
    injuries = {}
    for row in soup.select("div.lineupTable__row"):
        name_cell = row.select_one("a.lineupTable__cell--name")
        if not name_cell:
            continue
        name = name_cell.text.strip()
        absence_svg = row.select_one("svg.lineupTable__cell--absence")
        if not absence_svg:
            continue
        title_tag = absence_svg.select_one("title")
        if not title_tag:
            continue
        tooltip = title_tag.get_text(strip=True)
        m = re.search(r"^(.*?)(\d{2}\.\d{2}\.\d{4})$", tooltip)
        if m:
            reason, ret = m.group(1).strip(), m.group(2)
        else:
            reason, ret = tooltip, ""
        injuries[name] = (reason, ret)
    return injuries

def parse_match_dt(d_str, year):
    from datetime import datetime
    try:
        dd, mm = d_str.split(".")
        return datetime(year, int(mm), int(dd))
    except Exception:
        return None

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    current_year = 2026
    count_updated = 0
    for fn in sorted(os.listdir(CACHE_DIR)):
        if not fn.startswith("_live_cache_") or not fn.endswith(".json"):
            continue
        if target and target not in fn:
            continue
        team_id = fn.replace("_live_cache_", "").replace(".json", "")
        cache_path = os.path.join(CACHE_DIR, fn)
        try:
            cache = json.load(open(cache_path, "r", encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP {fn}: {e}")
            continue
        team_slug = cache.get("team", {}).get("slug", "")
        team_name = cache.get("team", {}).get("name", "")
        if not team_slug:
            print(f"  SKIP {fn}: no slug")
            continue
        print(f"\n=== {team_id} ({team_name}) ===")
        try:
            html = get_squad_html(team_id, team_slug)
        except Exception as e:
            print(f"  fetch failed: {e}")
            continue
        injuries = parse_injuries(html)
        if not injuries:
            print(f"  no injuries found")
            continue
        print(f"  injuries: {list(injuries.keys())}")
        matches = cache.get("matches", [])
        updated = 0
        for p in cache.get("players", []):
            pname = p.get("name", "")
            inj = injuries.get(pname)
            if not inj:
                surname = pname.split()[0].lower() if pname else ""
                for iname, ival in injuries.items():
                    if iname.split()[0].lower() == surname:
                        inj = ival
                        break
            if not inj:
                continue
            reason, ret = inj
            if not ret:
                continue
            from datetime import datetime
            try:
                d, m, y = ret.split(".")
                return_dt = datetime(int(y), int(m), int(d))
            except Exception:
                continue
            l3m = p.get("last3_missing", [None, None, None])
            while len(l3m) < 3:
                l3m.append(None)
            for i, m in enumerate(matches[:3]):
                md = parse_match_dt(m.get("date", ""), current_year)
                if not md:
                    continue
                if md < return_dt:
                    if l3m[i] is None or l3m[i] == "":
                        l3m[i] = reason or "Injury"
                        updated += 1
            p["last3_missing"] = l3m[:3]
        if updated > 0:
            cache["_cached_at"] = time.time()
            cache["last_updated"] = time.time()
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f"  updated {updated} cells")
            count_updated += 1
        else:
            print(f"  no changes")
    print(f"\nDone. {count_updated} cache files updated.")

if __name__ == "__main__":
    main()
