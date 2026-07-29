"""Fixture Congestion (FC) — calendar density metric.

Computed from the next 5 upcoming fixtures of a team.

== Algorithm (Jul 29 2026 v3) ==

For each pair of consecutive matches in the next 5:
    recovery_hours = (next_dt - prev_dt).total_seconds() / 3600
    recovery_days = round(recovery_hours / 24, 1)

Map each interval to load points:
    recovery_days >= 5 or above  ->  0 points
    4 days recovery              -> 20 points
    3 days recovery              -> 40 points
    2 days recovery              -> 70 points
    1 day recovery               -> 90 points
    0 days recovery              -> 100 points

average_load = sum(points) / number_of_intervals

short_rest_penalty (added on top of average_load):
    min_recovery_days (floor) == 0 -> +20
    min_recovery_days (floor) == 1 -> +15
    min_recovery_days (floor) == 2 -> +5
    min_recovery_days (floor) >= 3 -> +0

FC = clamp(average_load + short_rest_penalty, 0, 100)

== Status thresholds ==

  0-25  -> LOW      (green)
 26-50  -> NORMAL   (yellow)
 51-75  -> HIGH     (orange)
 76-100 -> EXTREME  (red)

== Change history ==

v1 (morning, Jul 29 2026):
  rest_days = (delta_days) - 1
  Calendar days between matches minus the match day itself.
  E.g. 14.08 00:30 -> 16.08 23:00 -> 1 day. WRONG.

v2 (afternoon, Jul 29 2026):
  recovery_days = floor(hours / 24)
  E.g. 71.5 hours -> 2.98 -> 2.0 days. WRONG (too low).

v3 (evening, Jul 29 2026):
  recovery_days = round(hours / 24, 1)
  E.g. 71.5 hours -> 2.98 -> 3.0 days (round).
  penalty uses floor(recovery_days) so the penalty
  thresholds match the original spec (0/1/2/3+).
  E.g. 2.9 days -> penalty uses floor(2.9)=2 -> +5.
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
            "average_recovery_days": 0.0,
            "minimum_recovery_days": 0,
            "next_matches_count": len(parsed),
            "recovery_intervals": [],
        }

    # Jul 29 2026 v3: round(hours/24, 1) instead of floor.
    intervals: List[float] = []
    interval_hours: List[float] = []
    for prev, nxt in zip(parsed, parsed[1:]):
        hours = (nxt - prev).total_seconds() / 3600.0
        recovery_days = round(hours / 24.0, 1)
        if recovery_days < 0:
            recovery_days = 0.0
        intervals.append(recovery_days)
        interval_hours.append(round(hours, 1))

    if not intervals:
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_recovery_days": 0.0,
            "minimum_recovery_days": 0,
            "next_matches_count": len(parsed),
            "recovery_intervals": [],
            "recovery_hours": [],
        }

    avg_recovery = sum(intervals) / len(intervals)

    # Penalty uses floor lookup (matches original 0/1/2/3+ thresholds).
    min_recovery = min(intervals)
    min_recovery_floor = int(min_recovery // 1)
    penalty = _penalty_for_min_rest(min_recovery_floor)

    # Load points use round() to nearest int (so 2.9 -> 3 days -> 40 pts).
    load_points = [_rest_to_load_points(round(r)) for r in intervals]
    average_load = sum(load_points) / len(load_points)

    fc_raw = average_load + penalty
    fc = max(0, min(100, int(round(fc_raw))))

    return {
        "fixture_congestion": fc,
        "status": _status_for(fc),
        "average_recovery_days": round(avg_recovery, 1),
        "minimum_recovery_days": min_recovery,
        "next_matches_count": len(parsed),
        "recovery_intervals": intervals,
        "recovery_hours": interval_hours,
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
        return "Medium Rotation Risk"
    if fc <= 75:
        return "High Rotation Risk"
    return "Very High Rotation Risk"

