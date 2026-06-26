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
    """Найти имя команды из существующего JSON-файла"""
    import glob
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "lineup_ai_*.json"))):
        if team_id in f and '_api' not in f:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                return data.get("team", {})
            except Exception:
                pass
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


async def fetch_team_live(team_id: str, force_refresh: bool = False) -> dict:
    """
    Главная функция: подгрузить актуальные данные команды с Soccerway.
    Возвращает dict в формате Player_Info.json.
    """
    # 0. Очищаем кэш при force_refresh
    if force_refresh:
        live_cache_path = _live_cache_path(team_id)
        if os.path.exists(live_cache_path):
            os.remove(live_cache_path)
            print(f"  Live cache cleared for {team_id}")
    
    # 1. Проверяем live-кеш
    if not force_refresh:
        cached = _load_live_cache(team_id)
        if cached:
            return cached

    # 2. Получаем имя команды
    meta = _find_team_meta(team_id)
    team_name = meta.get("name", team_id)

    # 3. Вызываем парсер
    from soccerway_parser import fetch_team_data, to_lineup_format

    team_data = await fetch_team_data(team_id, team_name, force_refresh=force_refresh)

    # 4. Конвертируем в формат lineup_team_view
    result = to_lineup_format(team_data)

    # 5. Сохраняем в кеш
    _save_live_cache(team_id, result)

    return result
