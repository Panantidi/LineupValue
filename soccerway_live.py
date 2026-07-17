#!/usr/bin/env python3
"""
Soccerway Live — обёртка для интеграции soccerway_parser.py с lineup_team_view.py.

Вызывает soccerway_parser.fetch_team_data() и возвращает результат
в формате Player_Info.json (совместимом с lineup_team_view.py).
"""

import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, "/home/openclaw/FormAlert")

DATA_DIR = "/home/openclaw/.openclaw/workspace"
CACHE_HOURS = 6


def _find_team_meta(team_id: str) -> dict:
    """Найти имя и slug команды из leagues_data.json"""
    import json
    leagues_path = "/home/openclaw/FormAlert/leagues_data.json"
    try:
        with open(leagues_path, 'r', encoding='utf-8') as f:
            leagues = json.load(f)
        for country, leagues_dict in leagues.items():
            for league_name, teams in leagues_dict.items():
                for team in teams:
                    if team.get("id") == team_id:
                        return {
                            "id": team_id,
                            "name": team.get("name", team_id),
                            "slug": team.get("slug", team.get("name", team_id).lower().replace(" ", "-"))
                        }
    except Exception as e:
        print(f"  [_find_team_meta] Error loading leagues_data: {e}")
    
    # Fallback: вернуть team_id как имя
    return {"id": team_id, "name": team_id, "slug": team_id}


def _live_cache_path(team_id: str) -> str:
    return os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")


def _load_live_cache(team_id: str) -> Optional[dict]:
    path = _live_cache_path(team_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ts = data.get("_cached_at", 0)
        if (time.time() - ts) > CACHE_HOURS * 3600:
            return None
        return data
    except Exception:
        return None


def _save_live_cache(team_id: str, data: dict):
    data["_cached_at"] = time.time()
    path = _live_cache_path(team_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Team IDs whose live cache is managed by a non-Soccerway source (e.g. Flashscore
# prefill). For these, fetch_team_live must NOT overwrite the cache — otherwise
# the Soccerway parser will clobber the prebuilt data on every page open.
PROTECTED_TEAMS_FILE = "/home/openclaw/.openclaw/workspace/_protected_teams.json"

def _load_protected_teams() -> set:
    try:
        with open(PROTECTED_TEAMS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

async def fetch_team_live(team_id: str, force_refresh: bool = False) -> dict:
    """
    Главная функция: подгрузить актуальные данные команды с Soccerway.
    Возвращает dict в формате Player_Info.json.
    """
    # Если команда в protect-list — НЕ перезаписываем кеш и возвращаем как есть
    if team_id in _load_protected_teams():
        cached = _load_live_cache(team_id)
        if cached:
            return cached
        # Нет кеша — возвращаем минимальный, чтобы UI не падал
        return {"team": {"id": team_id, "name": team_id, "slug": team_id}, "players": [], "matches": [], "coach": {"name": "", "nationality": ""}, "stadium": ""}

    # Проверяем live-кеш (пропускаем при force_refresh)
    if not force_refresh:
        cached = _load_live_cache(team_id)
        if cached:
            return cached

    # Получаем имя команды и slug
    meta = _find_team_meta(team_id)
    team_name = meta.get("name", team_id)
    team_slug = meta.get("slug", team_name.lower().replace(" ", "-"))

    # Используем быстрый HTTP-парсер
    from parse_team_fast import fetch_team_fast

    try:
        result = await fetch_team_fast(team_id, team_name, team_slug)
    except Exception as e:
        print(f"[fetch_team_live] fast parser failed: {e}, trying fallback...")
        # Fallback к медленному Playwright парсеру
        from soccerway_parser import fetch_team_data, to_lineup_format
        team_data = await fetch_team_data(team_id, team_name, force_refresh=force_refresh)
        result = to_lineup_format(team_data)

    # Backfill last3_missing for injured players (covers both fast + fallback paths).
    # If player has injury_return and the match is BEFORE that date, mark the cell as missing.
    from datetime import datetime as _dt
    def _parse_match_dt(d_str, year):
        try:
            dd, mm = d_str.split(".")
            return _dt(year, int(mm), int(dd))
        except Exception:
            return None
    current_year = _dt.now().year
    players = result.get("players", []) or []
    matches = result.get("matches", []) or []
    for p in players:
        inj_reason = p.get("injury_reason") or ""
        inj_return = p.get("injury_return") or ""
        if not inj_return:
            continue
        try:
            d, m, y = inj_return.split(".")
            return_dt = _dt(int(y), int(m), int(d))
        except Exception:
            continue
        l3m = p.get("last3_missing", [None, None, None])
        while len(l3m) < 3:
            l3m.append(None)
        for i, m in enumerate(matches[:3]):
            md = _parse_match_dt(m.get("date", ""), current_year)
            if not md:
                continue
            if md < return_dt and (l3m[i] is None or l3m[i] == ""):
                l3m[i] = inj_reason or "Injury"
        p["last3_missing"] = l3m[:3]

    # Сохраняем в кеш (перезаписываем)
    _save_live_cache(team_id, result)

    return result
