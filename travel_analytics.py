"""Stadium-to-stadium travel analytics (Sep 1 2026).

Feature requested by Max: a 🚌 button next to the Away team's Stadium
block in Match mode. Clicking it shows the travel analytics between the
two teams' stadiums:

    Distance — 260 km
    Difficulty — 🟢 Low
    Travel Index — 18/100
    Time Zone Difference — 0h

Data sources:
- Stadium name / city / country come from the team live caches
  (api_refresh writes stadium + city, team.country into
  _live_cache_<team_id>.json).
- Geocoding: Nominatim (OpenStreetMap), 1 req/sec with a proper
  User-Agent. Results cached in a module dict keyed by the query
  string so repeated renders / clicks never re-hit Nominatim.
- Distance: geopy.distance.geodesic (WGS-84), rounded to km.
- Time zones: timezonefinder over the geocoded coordinates.

Error contract (per user spec):
- Stadium not geocoded -> "Stadium not found"
- Time zone difference unavailable -> "N/A"
"""

import json
import os
import time
import urllib.parse
import urllib.request

CACHE_DIR = "/home/openclaw/.openclaw/workspace"

# --- Caches (per user spec: plain dicts, module-level) -------------------
# query string -> (lat, lon) or "NOT_FOUND"
_geo_cache = {}
# "lat,lon" -> IANA tz name or "NOT_FOUND"
_tz_cache = {}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "LineupValue-TravelAnalytics/1.0 (x11radar.ru; contact: admin@x11radar.ru)"

# Cache persisted to disk so restarts don't re-hit Nominatim either.
_GEO_CACHE_PATH = "/home/openclaw/.openclaw/workspace/_geo_cache.json"


def _load_geo_cache():
    if _geo_cache:
        return
    try:
        with open(_GEO_CACHE_PATH, "r", encoding="utf-8") as f:
            _geo_cache.update(json.load(f))
    except Exception:
        pass


def _save_geo_cache():
    try:
        with open(_GEO_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_geo_cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _team_info(team_id):
    """Return (stadium_name, city, country) from the team's live cache.

    Country comes from team.country (e.g. "France"). Missing pieces are
    returned as "" — the caller builds the best geocode query it can.
    """
    path = os.path.join(CACHE_DIR, f"_live_cache_{team_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return "", "", ""
    team = data.get("team") or {}
    stadium = (data.get("stadium") or team.get("stadium") or "").strip()
    city = (data.get("city") or team.get("city") or "").strip()
    country = (team.get("country") or "").strip()
    return stadium, city, country


def _nominatim(query):
    """Geocode one query. Returns (lat, lon) or None. Cached."""
    _load_geo_cache()
    if query in _geo_cache:
        v = _geo_cache[query]
        return None if v == "NOT_FOUND" else (v[0], v[1])
    time.sleep(1)  # Nominatim usage policy: max 1 req/sec
    try:
        url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "limit": 1}
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode("utf-8"))
        if rows and isinstance(rows, list):
            lat = float(rows[0]["lat"])
            lon = float(rows[0]["lon"])
            _geo_cache[query] = (lat, lon)
        else:
            _geo_cache[query] = "NOT_FOUND"
    except Exception:
        _geo_cache[query] = "NOT_FOUND"
    _save_geo_cache()
    v = _geo_cache[query]
    return None if v == "NOT_FOUND" else (v[0], v[1])


def _geocode_stadium(stadium, city, country):
    """Two-stage geocoding: with country first, fallback without.

    Returns (lat, lon) or None (-> "Stadium not found").
    """
    if not stadium:
        return None
    if stadium and city and country:
        c = _nominatim(f"{stadium}, {city}, {country}")
        if c:
            return c
    if stadium and city:
        return _nominatim(f"{stadium}, {city}")
    return _nominatim(stadium) if stadium else None


def _timezone_at(lat, lon):
    """IANA timezone name for coordinates, or None."""
    key = f"{round(lat, 3)},{round(lon, 3)}"
    if key in _tz_cache:
        v = _tz_cache[key]
        return None if v == "NOT_FOUND" else v
    tz_name = None
    try:
        from timezonefinder import TimezoneFinder
        tz_name = TimezoneFinder().timezone_at(lat=lat, lng=lon)
    except Exception:
        tz_name = None
    _tz_cache[key] = tz_name or "NOT_FOUND"
    return tz_name


def _tz_offset_hours(tz_name):
    """Current UTC offset of a timezone in float hours, or None."""
    if not tz_name:
        return None
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo  # py3.9+
            dt = datetime.now(ZoneInfo(tz_name))
        except Exception:
            import pytz
            dt = datetime.now(pytz.timezone(tz_name))
        off = dt.utcoffset()
        return off.total_seconds() / 3600.0 if off else None
    except Exception:
        return None


def difficulty_label(km):
    """New scale (Sep 2 2026): 0-350 Low / 351-550 Normal / 551-1000 High / 1000+ Extreme."""
    if km <= 350:
        return "🟢 Low"
    if km <= 550:
        return "🟡 Normal"
    if km <= 1000:
        return "🟠 High"
    return "🔴 Extreme"


# Distance Score bands (Sep 2 2026): (km_min, km_max, score_min, score_max).
# Linear interpolation inside the band, rounded to int. 5001+ km -> 80.
DISTANCE_BANDS = [
    (0, 100, 0, 5),
    (101, 300, 6, 15),
    (301, 500, 16, 25),
    (501, 750, 26, 35),
    (751, 1000, 36, 45),
    (1001, 1250, 46, 55),
    (1251, 1500, 56, 65),
    (1501, 2000, 66, 70),
    (2001, 3000, 71, 74),
    (3001, 4000, 75, 77),
    (4001, 5000, 78, 79),
    (5001, None, 80, 80),  # None = open-ended
]


def calculate_distance_score(km):
    """Distance Score per band table with linear interpolation."""
    for lo, hi, slo, shi in DISTANCE_BANDS:
        if hi is None or km <= hi:
            if km < lo:
                continue
            if hi is None:
                return shi
            if shi == slo:
                return slo
            val = slo + (km - lo) / (hi - lo) * (shi - slo)
            return int(round(val))
    return 80


def calculate_timezone_score(hours):
    """Time Zone Score: 0->0 1->2 2->4 3->6 4->8 5->10 6->12 7->15 8+->20."""
    if hours is None:
        return None
    h = int(hours)
    if h >= 8:
        return 20
    return {0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 10, 6: 12, 7: 15}.get(h, 0)


def calculate_travel_index(km, tz_hours=None):
    """Travel Index = Distance Score + Time Zone Score (max 100)."""
    return calculate_distance_score(km) + (calculate_timezone_score(tz_hours) or 0)


def travel_index_emoji(idx):
    if idx <= 25:
        return "🟢 Low"
    if idx <= 50:
        return "🟡 Normal"
    if idx <= 75:
        return "🟠 High"
    return "🔴 Extreme"


def compute_travel(home_team_id, away_team_id):
    """Full analytics between two teams' stadiums.

    Returns a dict:
        {
          "ok": bool,
          "text": "Distance — ...\nDifficulty — ...\n...",  # ready to show
          "distance_km": int | None,
          "home": {...}, "away": {...},
        }
    """
    h_st, h_city, h_country = _team_info(home_team_id)
    a_st, a_city, a_country = _team_info(away_team_id)

    result = {
        "ok": False,
        "distance_km": None,
        "home": {"team_id": home_team_id, "stadium": h_st, "city": h_city, "country": h_country, "coords": None},
        "away": {"team_id": away_team_id, "stadium": a_st, "city": a_city, "country": a_country, "coords": None},
    }

    h_coord = _geocode_stadium(h_st, h_city, h_country)
    a_coord = _geocode_stadium(a_st, a_city, a_country)

    result["home"]["coords"] = h_coord
    result["away"]["coords"] = a_coord

    if not h_coord or not a_coord:
        result["text"] = "Stadium not found"
        return result

    try:
        from geopy.distance import geodesic
        km = int(round(geodesic(h_coord, a_coord).km))
    except Exception:
        km = None
    if km is None:
        result["text"] = "Stadium not found"
        return result

    result["ok"] = True
    result["distance_km"] = km

    lines = [
        f"Distance — {km} km",
        f"Difficulty — {difficulty_label(km)}",
    ]

    # TZ diff FIRST (it feeds the new Travel Index = dist_score + tz_score)
    tz_diff = None
    try:
        h_tz = _timezone_at(h_coord[0], h_coord[1])
        a_tz = _timezone_at(a_coord[0], a_coord[1])
        h_off = _tz_offset_hours(h_tz)
        a_off = _tz_offset_hours(a_tz)
        if h_off is not None and a_off is not None:
            tz_diff = int(round(abs(h_off - a_off)))
    except Exception:
        tz_diff = None
    result["tz_diff"] = tz_diff
    # Sep 2 2026 — Travel Index = Distance Score + Time Zone Score (max 100)
    lines.append(f"Travel Index — {calculate_travel_index(km, tz_diff)}/100")
    if tz_diff is None:
        lines.append("Time Zone Difference — N/A")
    else:
        lines.append(f"Time Zone Difference — {tz_diff}h")

    result["text"] = "\n".join(lines)
    return result