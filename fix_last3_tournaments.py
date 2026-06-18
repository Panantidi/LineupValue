#!/usr/bin/env python3
"""Repair Last 3 tournament labels in existing FormAlert caches/DB versions.

Uses the same per-match Soccerway header logic as fetch_team.py:
for each cached match URL, open the team's results page and map each match mid
only to the nearest preceding headerLeague__wrapper, not the whole results
container. This fixes cases where mixed competitions on one page caused e.g.
Conference League matches to be labeled PL.
"""
import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = "/home/openclaw/.openclaw/workspace"
DB_PATH = os.path.join(ROOT, "formalert.db")
BASE = "https://www.soccerway.com"

sys.path.insert(0, ROOT)
import app  # noqa: E402

COMP_MAP = {
    "ligue 1": "L1", "ligue 2": "L2",
    "premier league": "PL", "championship": "CH",
    "bundesliga": "BL", "2. bundesliga": "B2",
    "serie a": "SA", "la liga": "LL", "laliga": "LL",
    "eredivisie": "ER", "liga portugal": "LP", "jupiler pro league": "JPL",
    "super lig": "SL", "super league": "SUL", "superliga": "SUP",
    "allsvenskan": "ALL", "eliteserien": "ELI",
    "champions league": "CL", "europa league": "EL", "conference league": "ECL",
    "dfb pokal": "DFB", "fa cup": "FA", "efl cup": "LC", "league cup": "LC",
    "coupe de france": "CDF", "copa del rey": "CDR", "coppa italia": "CI",
    "club friendlies": "FR", "friendlies": "FR", "friendly": "FR",
    "national cup": "CUP", "world championship": "WC",
}
FULL_NAMES = {
    "L1": "Ligue 1", "L2": "Ligue 2", "PL": "Premier League", "CH": "Championship",
    "BL": "Bundesliga", "B2": "2. Bundesliga", "SA": "Serie A", "LL": "La Liga",
    "ER": "Eredivisie", "LP": "Liga Portugal", "JPL": "Jupiler Pro League",
    "SL": "Süper Lig", "SUL": "Super League", "SUP": "Superliga", "ALL": "Allsvenskan",
    "ELI": "Eliteserien", "CL": "Champions League", "EL": "Europa League", "ECL": "Conference League",
    "DFB": "DFB Pokal", "FA": "FA Cup", "LC": "League Cup", "CDF": "Coupe de France",
    "CDR": "Copa del Rey", "CI": "Coppa Italia", "CUP": "National Cup", "FR": "Friendly", "UNK": "Other Competition", "WC": "World Championship",
}


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def comp_from_header(header_text: str) -> str:
    lt = (header_text or "").lower()
    for key, val in COMP_MAP.items():
        if key in lt:
            return val
    return "UNK"


def mid_from_url(url: str) -> str:
    m = re.search(r"[?&]mid=([A-Za-z0-9]+)", url or "")
    return m.group(1) if m else ""


def results_url(team):
    slug = (team or {}).get("slug") or ""
    tid = (team or {}).get("id") or ""
    if not slug or not tid:
        return ""
    return f"{BASE}/team/{slug}/{tid}/results/"


def parse_results_tournaments(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    mapping = {}
    for leagues in soup.select('div[class*="leagues"]'):
        current_header = ""
        for child in leagues.find_all(['div', 'section'], recursive=False):
            classes = " ".join(child.get("class", []))
            if "headerLeague" in classes:
                current_header = child.get_text(" ", strip=True)
                continue
            if "event__match" not in classes:
                continue
            a = child.find("a", href=re.compile(r"/(match|game)/"))
            if not a:
                continue
            href = a.get("href", "")
            mid = mid_from_url(href)
            if not mid:
                continue
            mapping[mid] = {
                "tournament": comp_from_header(current_header),
                "header": current_header,
            }
    return mapping


async def fetch_results_pages(teams):
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}, locale='en-US'
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        for tid, team in teams.items():
            url = results_url(team)
            if not url:
                continue
            log(f"FETCH_RESULTS {tid} {team.get('name')} {url}")
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                await page.wait_for_timeout(4000)
                for _ in range(6):
                    await page.evaluate("window.scrollBy(0, 700)")
                    await page.wait_for_timeout(350)
                html = await page.content()
                out[tid] = parse_results_tournaments(html)
                log(f"PARSED {tid} mids={len(out[tid])}")
            except Exception as exc:
                log(f"ERROR {tid} {exc}")
            await page.wait_for_timeout(750)
        await browser.close()
    return out


def all_configured_teams():
    with open(os.path.join(ROOT, "leagues_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    teams = {}
    for country, leagues in data.items():
        if not isinstance(leagues, dict):
            continue
        for league, items in leagues.items():
            if not isinstance(items, list):
                continue
            for t in items:
                if isinstance(t, dict) and t.get("id"):
                    teams[str(t["id"])] = dict(t)
    return teams


def loaded_team_ids():
    ids = set()
    for name in os.listdir(CACHE_DIR):
        m = re.match(r"_live_cache_(.+)\.json$", name)
        if not m:
            continue
        try:
            data = json.load(open(os.path.join(CACHE_DIR, name), encoding="utf-8"))
            if data.get("players") and data.get("matches"):
                ids.add(m.group(1))
        except Exception:
            pass
    return ids


def repair_one_cache(tid, mapping, team_lookup):
    path = os.path.join(CACHE_DIR, f"_live_cache_{tid}.json")
    if not os.path.exists(path):
        return False, []
    data = json.load(open(path, encoding="utf-8"))
    changes = []
    for m in data.get("matches", []):
        mid = str(m.get("mid") or mid_from_url(m.get("url", "")))
        new = (mapping.get(tid) or {}).get(mid, {}).get("tournament")
        if new and new != "UNK" and new != (m.get("tournament") or m.get("comp")):
            old = m.get("tournament") or m.get("comp") or ""
            m["tournament"] = new
            if "comp" in m:
                m["comp"] = new
            changes.append((mid, old, new, m.get("score", "")))
    if changes:
        data.setdefault("team", {}).update({k: v for k, v in (team_lookup.get(tid) or {}).items() if k in ("id", "name", "slug")})
        data["last_updated"] = time.time()
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        app._save_team_version(tid, data)
        return True, changes
    return False, []


async def main():
    team_lookup = all_configured_teams()
    ids = loaded_team_ids()
    teams = {tid: team_lookup.get(tid, {}) for tid in ids if team_lookup.get(tid, {}).get("slug")}
    log(f"LOADED_WITH_CONFIG {len(teams)}")
    mapping = await fetch_results_pages(teams)
    total_changes = 0
    for tid in sorted(teams):
        changed, changes = repair_one_cache(tid, mapping, team_lookup)
        if changed:
            total_changes += len(changes)
            for mid, old, new, score in changes:
                log(f"CHANGE {tid} {teams[tid].get('name')} mid={mid} {old}->{new} {score}")
    log(f"DONE changes={total_changes}")


if __name__ == "__main__":
    asyncio.run(main())
