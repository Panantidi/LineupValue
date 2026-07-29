"""Fixture Congestion (FC) — calendar density metric.

Computed from the next 5 upcoming fixtures of a team.

== Algorithm ==

For each pair of consecutive matches in the next 5:
    rest_days = next_match_date - current_match_date - 1

Map each interval to a load points (lower rest = higher load):
    5+ days =  0 points
    4 days   = 20 points
    3 days   = 40 points
    2 days   = 70 points
    1 day    = 90 points
    0 days   = 100 points

average_load = sum(points) / number_of_intervals

short_rest_penalty (added on top of average_load):
    min_rest_days == 0 -> +20
    min_rest_days == 1 -> +15
    min_rest_days == 2 -> +5
    min_rest_days >= 3 -> +0

FC = clamp(average_load + short_rest_penalty, 0, 100)

== Status thresholds ==

  0-25  -> LOW      (green)
 26-50  -> NORMAL   (yellow)
 51-75  -> HIGH     (orange)
 76-100 -> EXTREME  (red)
"""

from __future__ import annotations

from datetime import datetime
from typing import List

# Map: rest_days -> points (anything >= 5 -> 0 points)
_LOAD_BY_REST_DAYS = {
    0: 100,
    1: 90,
    2: 70,
    3: 40,
    4: 20,
}
_DEFAULT_LOAD = 0  # 5+ days


def _rest_to_load_points(rest_days: int) -> int:
    """Map rest interval (days) to load points."""
    if rest_days < 0:
        return _LOAD_BY_REST_DAYS[0]
    if rest_days >= 5:
        return _DEFAULT_LOAD
    return _LOAD_BY_REST_DAYS.get(rest_days, _DEFAULT_LOAD)


def _status_for(fc: float) -> str:
    """Classify FC value into status bucket."""
    if fc <= 25:
        return "LOW"
    if fc <= 50:
        return "NORMAL"
    if fc <= 75:
        return "HIGH"
    return "EXTREME"


def _penalty_for_min_rest(min_rest_days: int) -> int:
    """Short-rest penalty applied on top of average load."""
    if min_rest_days <= 0:
        return 20
    if min_rest_days == 1:
        return 15
    if min_rest_days == 2:
        return 5
    return 0


def compute_fixture_congestion(fixtures: list) -> dict:
    """Compute Fixture Congestion score from a list of fixtures.

    Each fixture dict is expected to have either:
      - "timestamp": unix epoch seconds
    OR
      - "date" + "time": "dd/mm" + "HH:MM"

    Returns a dict suitable for caching in the team live_cache.

    Schema:
        {
          "fixture_congestion": 90,
          "status": "EXTREME",
          "average_rest_days": 1.8,
          "minimum_rest_days": 1,
          "next_matches_count": 5,
          "rest_intervals": [2, 2, 1, 2]
        }
    """
    if not fixtures:
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_rest_days": 0.0,
            "minimum_rest_days": 0,
            "next_matches_count": 0,
            "rest_intervals": [],
        }

    # Convert each fixture to a datetime. Prefer timestamp.
    parsed: List[datetime] = []
    for f in fixtures[:5]:
        ts = f.get("timestamp")
        if ts:
            try:
                parsed.append(datetime.utcfromtimestamp(int(ts)))
                continue
            except (TypeError, ValueError, OSError):
                pass
        date_str = (f.get("date") or "").strip()
        time_str = (f.get("time") or "").strip()
        if not date_str:
            continue
        try:
            parts = date_str.split("/")
            day_i, month_i = int(parts[0]), int(parts[1])
            now = datetime.utcnow()
            year_i = now.year
            try:
                candidate = datetime(year_i, month_i, day_i, 12, 0)
                if candidate < now:
                    candidate = datetime(year_i + 1, month_i, day_i, 12, 0)
                    year_i = year_i + 1
            except ValueError:
                continue
            hour_i, minute_i = 12, 0
            if time_str and ":" in time_str:
                try:
                    h, m = time_str.split(":")[:2]
                    hour_i, minute_i = int(h), int(m)
                except ValueError:
                    pass
            parsed.append(datetime(year_i, month_i, day_i, hour_i, minute_i))
        except (ValueError, IndexError):
            continue

    parsed.sort()
    if len(parsed) < 2:
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_rest_days": 0.0,
            "minimum_rest_days": 0,
            "next_matches_count": len(parsed),
            "rest_intervals": [],
        }

    intervals: List[int] = []
    for prev, nxt in zip(parsed, parsed[1:]):
        delta_days = (nxt - prev).days
        rest = max(0, delta_days - 1)
        intervals.append(rest)

    if not intervals:
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_rest_days": 0.0,
            "minimum_rest_days": 0,
            "next_matches_count": len(parsed),
            "rest_intervals": [],
        }

    avg_rest = sum(intervals) / len(intervals)
    min_rest = min(intervals)

    load_points = [_rest_to_load_points(r) for r in intervals]
    average_load = sum(load_points) / len(load_points)
    penalty = _penalty_for_min_rest(min_rest)

    fc_raw = average_load + penalty
    fc = max(0, min(100, int(round(fc_raw))))

    return {
        "fixture_congestion": fc,
        "status": _status_for(fc),
        "average_rest_days": round(avg_rest, 1),
        "minimum_rest_days": min_rest,
        "next_matches_count": len(parsed),
        "rest_intervals": intervals,
    }


def progress_bar(fc: int, width: int = 10) -> str:
    """Render a unicode progress bar for the FC value (block characters)."""
    fc = max(0, min(100, int(fc)))
    filled = round(fc / 10)
    if filled > width:
        filled = width
    return "\u2588" * filled + "\u2591" * (width - filled)


def risk_label(fc: int) -> str:
    """Return a human-readable rotation risk label."""
    if fc <= 25:
        return "Low Rotation Risk"
    if fc <= 50:
        return "Moderate Rotation Risk"
    if fc <= 75:
        return "High Rotation Risk"
    return "Very High Rotation Risk"

