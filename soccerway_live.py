#!/usr/bin/env python3
"""
Soccerway Live Fetcher — парсинг данных команды через Soccerway block API.

Использует httpx (без Playwright) для быстрых запросов к:
  /a/block_team_squad  — состав + статистика (Total)
  /a/block_team_summary — coach, stadium, info
  Страница матча        — STARTING LINEUPS / SUBSTITUTES для last3

Формат ответа — совместим с Player_Info.json:
{
  "team": { "id", "name", "slug", "league", "country" },
  "coach": { "name", "nationality" },
  "stadium": "...",
  "matches": [ { "date", "comp", "url" }, ... ]   — последние 3
  "players": [ { "number", "name", "national", "position", "age",
                 "apps", "min", "goal", "assist", "yellow_card", "red_card",
                 "profile_path", "market_value",
                 "last3": ["START"|"SUB"|"—", ...] }, ... ]
}
"""

import re
import json
import time
import os
import httpx
from datetime import datetime
from typing import Optional

SOCCERWAY_BASE = "https://us.soccerway.com"
DATA_DIR = "/home/openclaw/.openclaw/workspace"
CACHE_HOURS = 6  # кеш до 6 часов

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


def _cache_path(team_id: str) -> str:
    return os.path.join(DATA_DIR, f"_live_cache_{team_id}.json")


def _load_cache(team_id: str) -> Optional[dict]:
    path = _cache_path(team_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("_cached_at", 0)
        if (time.time() - ts) > CACHE_HOURS * 3600:
            return None
        return data
    except Exception:
        return None


def _save_cache(team_id: str, data: dict):
    data["_cached_at"] = time.time()
    path = _cache_path(team_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _find_team_json(team_id: str) -> Optional[str]:
    """Найти существующий JSON файл команды (для получения имени, лиги и т.д.)"""
    import glob
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "lineup_ai_*.json"))):
        if team_id in f and '_api' not in f:
            return f
    return None


def _load_team_meta(team_id: str) -> dict:
    """Загрузить метаданные команды из существующего JSON"""
    path = _find_team_json(team_id)
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("team", {})
        except Exception:
            pass
    return {"id": team_id, "name": team_id, "slug": team_id}


async def _http_get(client: httpx.AsyncClient, url: str) -> str:
    """Выполнить GET-запрос с обработкой ошибок"""
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def _parse_squad_table(html: str) -> list:
    """
    Парсинг таблицы состава из HTML Soccerway.
    Ищет строки с игроками в секции Total.
    """
    players = []

    # Найти секцию "Total" — ищем таблицу после заголовка Total
    total_section = html
    total_marker = re.search(r'id="team_squad"[^>]*>.*?(<table[^>]*>.*?</table>)', html, re.DOTALL | re.IGNORECASE)
    if total_marker:
        total_section = total_marker.group(1)

    # Найти все строки таблицы
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', total_section, re.DOTALL | re.IGNORECASE)

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 8:
            continue

        # Найти имя игрока (ссылка на /player/)
        name_match = re.search(r'<a[^>]+href="([^"]*/player/[^"]*)"[^>]*>(.*?)</a>', row, re.DOTALL)
        if not name_match:
            continue

        profile_path = name_match.group(1).strip()
        name_raw = re.sub(r'<[^>]+>', '', name_match.group(2)).strip()

        if not name_raw or name_raw in ('Name', 'Player', 'Position'):
            continue

        # Номер (первая ячейка с цифрой)
        number = "-"
        for cell in cells[:2]:
            txt = re.sub(r'<[^>]+>', '', cell).strip()
            if txt.isdigit():
                number = txt
                break

        # Национальность (ищем alt у флага)
        national = "-"
        nat_match = re.search(r'class="flag"\s*(?:alt|title)="([^"]+)"', row)
        if not nat_match:
            nat_match = re.search(r'<img[^>]*class="[^"]*flag[^"]*"[^>]*alt="([^"]+)"', row)
        if not nat_match:
            # Альтернативный паттерн — title у ссылки
            nat_match = re.search(r'title="([^"]+)"[^>]*class="flag', row)
        if nat_match:
            national = nat_match.group(1).strip()

        # Позиция
        position = "-"
        pos_text = re.sub(r'<[^>]+>', '', cells[2] if len(cells) > 2 else "").strip() if len(cells) > 2 else ""
        pos_map = {
            "G": "GK", "GK": "GK", "Goalkeeper": "GK",
            "D": "DF", "DF": "DF", "Defender": "DF",
            "M": "MF", "MF": "MF", "Midfielder": "MF",
            "F": "FW", "FW": "FW", "Forward": "FW", "Attacker": "FW",
        }
        for key, val in pos_map.items():
            if pos_text.upper().startswith(key.upper()):
                position = val
                break

        # Возраст
        age = "-"
        for cell in cells[3:5]:
            txt = re.sub(r'<[^>]+>', '', cell).strip()
            if txt.isdigit() and int(txt) < 55:
                age = txt
                break

        # Статистика — Apps, Min, G, A, YC, RC (ячейки после позиции и возраста)
        stats_cells = cells[4:] if len(cells) > 6 else cells[3:]
        stats_values = []
        for cell in stats_cells:
            txt = re.sub(r'<[^>]+>', '', cell).strip()
            txt = txt.replace('\xa0', '').replace(',', '')
            if txt.isdigit():
                stats_values.append(txt)
            elif txt == '-' or txt == '—' or txt == '0':
                stats_values.append("0")
            else:
                stats_values.append(txt)

        # Назначаем статистику по позиции
        # Soccerway squad: №, Name, Nat, Pos, Age, Apps, Min, G, A, YC, RC
        # Но может отличаться — пытаемся угадать
        apps = stats_values[0] if len(stats_values) > 0 else "-"
        mins = stats_values[1] if len(stats_values) > 1 else "-"
        goals = stats_values[2] if len(stats_values) > 2 else "-"
        assists = stats_values[3] if len(stats_values) > 3 else "-"
        yc = stats_values[4] if len(stats_values) > 4 else "-"
        rc = stats_values[5] if len(stats_values) > 5 else "-"

        players.append({
            "number": number,
            "name": name_raw,
            "national": national,
            "position": position,
            "age": age,
            "apps": apps,
            "min": mins,
            "goal": goals,
            "assist": assists,
            "yellow_card": yc,
            "red_card": rc,
            "profile_path": profile_path,
            "market_value": "-",
            "last3": ["—", "—", "—"],
        })

    return players


def _parse_coach_stadium(html: str) -> dict:
    """Извлечь Coach и Stadium из HTML страницы команды"""
    result = {"coach": {}, "stadium": ""}

    # Coach
    coach_match = re.search(
        r'(?:Coach|Trainer|Manager)[^<]*<[^>]*>([^<]+)', html, re.IGNORECASE
    )
    if coach_match:
        result["coach"]["name"] = coach_match.group(1).strip()

    # Coach nationality
    coach_nat = re.search(
        r'(?:Coach|Trainer|Manager).*?<img[^>]*class="[^"]*flag[^"]*"[^>]*title="([^"]+)"',
        html, re.DOTALL | re.IGNORECASE
    )
    if coach_nat:
        result["coach"]["nationality"] = coach_nat.group(1).strip()

    # Stadium
    stadium_match = re.search(
        r'(?:Stadium|Venue)[^<]*<[^>]*>([^<]+)', html, re.IGNORECASE
    )
    if stadium_match:
        result["stadium"] = stadium_match.group(1).strip()

    return result


def _parse_recent_matches(html: str, team_name: str) -> list:
    """
    Извлечь последние 3 матча из секции Results.
    Возвращает список: [{ "date": "DD.MM", "comp": "L1", "url": "..." }, ...]
    """
    matches = []

    # Ищем ссылки на матчи
    game_links = re.findall(
        r'<a[^>]+href="([^"]*/game/[^"]*)"[^>]*>.*?</a>',
        html, re.DOTALL | re.IGNORECASE
    )

    # Ищем даты рядом с матчами
    date_pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4}|\d{2}\.\d{2}\.\d{4}|\d{1,2}\s+\w{3}\s+\d{4})',
        re.IGNORECASE
    )

    # Компоненты соревнований
    comp_map = {
        "ligue-1": "L1", "ligue-2": "L2", "premier-league": "PL",
        "championship": "CH", "la-liga": "LL", "laliga": "LL",
        "serie-a": "SA", "bundesliga": "BL", "bundesliga-2": "B2",
        "eredivisie": "ER", "liga-portugal": "LP", "jupiler-pro-league": "JPL",
        "super-lig": "SL", "super-league": "SUL", "superliga": "SUP",
        "allsvenskan": "ALL", "eliteserien": "ELI",
        "premier-league": "RFPL", "first-league": "FL",
        "fa-cup": "FA", "coupe-de-france": "CDF", "coupe-de-la-ligue": "CDL",
        "champions-league": "CL", "europa-league": "EL", "conference-league": "ECL",
        "dfb-pokal": "DFB", "copa-del-rey": "CDR", "coppa-italia": "CI",
        "league-cup": "LC", "cup": "CUP",
    }

    seen = set()
    for link in game_links[:10]:  # берем первые 10, потом фильтруем
        url = link if link.startswith("http") else SOCCERWAY_BASE + link
        # Извлечь соревнование из URL
        comp = "??"
        for key, val in comp_map.items():
            if key in url.lower():
                comp = val
                break

        # Уникальный ID матча
        mid_match = re.search(r'[?&]mid=([^&]+)', url)
        mid = mid_match.group(1) if mid_match else url[-20:]
        if mid in seen:
            continue
        seen.add(mid)

        matches.append({
            "date": "",  # заполнится при парсинге матча
            "comp": comp,
            "url": url,
        })

        if len(matches) >= 3:
            break

    return matches


async def _parse_match_lineups(client: httpx.AsyncClient, match_url: str) -> dict:
    """
    Парсинг страницы матча — извлечь STARTING LINEUPS и SUBSTITUTES.
    Возвращает {"starters": [name, ...], "subs": [name, ...]}
    """
    result = {"starters": [], "subs": [], "date": ""}

    try:
        html = await _http_get(client, match_url)
    except Exception:
        return result

    # Дата матча
    date_match = re.search(
        r'(\d{2}/\d{2}/\d{4})', html
    )
    if date_match:
        raw = date_match.group(1)
        parts = raw.split("/")
        if len(parts) == 3:
            result["date"] = f"{parts[0]}.{parts[1]}"

    # Начальный состав
    lineup_section = re.search(
        r'(?:Starting\s*lineups?|STARTING\s*LINEUPS?)[^<]*(.*?)(?:Substitutes|SUBSTITUTES|</div>)',
        html, re.DOTALL | re.IGNORECASE
    )
    if lineup_section:
        section = lineup_section.group(1)
        player_links = re.findall(r'<a[^>]*href="[^"]*/player/[^"]*"[^>]*>([^<]+)</a>', section)
        result["starters"] = [p.strip() for p in player_links if p.strip()]

    # Запасные
    sub_section = re.search(
        r'(?:Substitutes|SUBSTITUTES)[^<]*(.*?)(?:Starting|STARTING|Coach|</div>|<h\d)',
        html, re.DOTALL | re.IGNORECASE
    )
    if sub_section:
        section = sub_section.group(1)
        player_links = re.findall(r'<a[^>]*href="[^"]*/player/[^"]*"[^>]*>([^<]+)</a>', section)
        result["subs"] = [p.strip() for p in player_links if p.strip()]

    return result


async def fetch_team_live(team_id: str) -> dict:
    """
    Главная функция: подгрузить актуальные данные команды с Soccerway.

    Возвращает dict в формате Player_Info.json.
    """
    # 1. Проверяем кеш
    cached = _load_cache(team_id)
    if cached:
        return cached

    # 2. Загружаем метаданные команды
    team_meta = _load_team_meta(team_id)
    team_name = team_meta.get("name", team_id)
    team_slug = team_meta.get("slug", team_name.lower().replace(" ", "-"))

    # 3. Формируем URL состава
    squad_url = f"{SOCCERWAY_BASE}/team/{team_slug}/{team_id}/squad/"

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # 4. Загружаем страницу состава
        try:
            squad_html = await _http_get(client, squad_url)
        except httpx.HTTPStatusError as e:
            raise Exception(f"Soccerway вернул ошибку {e.response.status_code}")
        except httpx.RequestError as e:
            raise Exception(f"Не удалось подключиться к Soccerway: {e}")

        # 5. Парсим состав
        players = _parse_squad_table(squad_html)
        if not players:
            raise Exception("Не удалось найти данные о составе на странице Soccerway")

        # 6. Парсим Coach и Stadium
        coach_stadium = _parse_coach_stadium(squad_html)

        # 7. Парсим последние 3 матча
        matches = _parse_recent_matches(squad_html, team_name)

        # 8. Для каждого матча — загружаем составы и заполняем last3
        if matches:
            # Собираем имена игроков в lowercase для быстрого поиска
            player_name_map = {}
            for p in players:
                key = p["name"].lower().strip()
                player_name_map[key] = p

            for match_idx, match in enumerate(matches[:3]):
                match_data = await _parse_match_lineups(client, match["url"])

                # Обновляем дату матча
                if match_data["date"]:
                    match["date"] = match_data["date"]

                # Отмечаем START
                for name in match_data["starters"]:
                    key = name.lower().strip()
                    if key in player_name_map:
                        player_name_map[key]["last3"][match_idx] = "START"

                # Отмечаем SUB
                for name in match_data["subs"]:
                    key = name.lower().strip()
                    if key in player_name_map:
                        player_name_map[key]["last3"][match_idx] = "SUB"

        # 9. Собираем итоговый JSON
        result = {
            "team": {
                "id": team_id,
                "name": team_name,
                "slug": team_slug,
                "league": team_meta.get("league", ""),
                "country": team_meta.get("country", ""),
            },
            "coach": coach_stadium.get("coach", {}),
            "stadium": coach_stadium.get("stadium", ""),
            "matches": matches[:3],
            "players": players,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

        # 10. Сохраняем в кеш
        _save_cache(team_id, result)

        return result
