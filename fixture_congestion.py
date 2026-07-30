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
  WRONG.

v2 (afternoon, Jul 29 2026):
  recovery_days = floor(hours / 24)
  WRONG (too low).

v3 (evening, Jul 29 2026):
  recovery_days = round(hours / 24, 1)
  penalty uses floor(recovery_days).

v4 (late evening, Jul 29 2026):
  penalty uses HOURS (not days) so that
  single-day matches with hour-level density
  (e.g. back-to-back matches at 14:00 and 15:00
  = 1 hour gap) are correctly flagged as critical.
  Added minimum_recovery_hours to JSON.
  Load points still use round(days) so
  0.04 days -> round -> 0 days -> 100 pts (critical).

Penalty thresholds (v4, hours-based):
  recovery_hours < 24  -> +20 (critical, same-day)
  24-47 hours (1 day)  -> +15
  48-71 hours (2 days) -> +5
  72+ hours (3+ days)  -> +0
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

# Maximum travel penalty applied on top of FC base.
# Caps total logistics bonus so a chain of A->A transitions
# cannot inflate FC beyond +10.
MAX_TRAVEL_PENALTY = 10


def _rest_to_load_points(rest_days: int) -> int:
    """Map rest interval (days) to load points."""
    if rest_days < 0:
        return _LOAD_BY_REST_DAYS[0]
    if rest_days >= 5:
        return _DEFAULT_LOAD
    return _LOAD_BY_REST_DAYS.get(rest_days, _DEFAULT_LOAD)


def _status_for(fc: float) -> str:
    """Classify FC value into status bucket.

    New thresholds (Jul 29 2026, user spec):
      0-30   -> LOW
      31-55  -> NORMAL
      56-80  -> HIGH
      81-100 -> EXTREME
    """
    if fc <= 30:
        return "LOW"
    if fc <= 55:
        return "NORMAL"
    if fc <= 80:
        return "HIGH"
    return "EXTREME"


def _penalty_for_min_rest_hours(min_recovery_hours: float) -> int:
    """Short-rest penalty applied on top of average load.

    Hours-based (Jul 29 2026 v4): so a 1-hour gap
    between two matches on the same day is correctly
    critical, not just "0 days".

    Thresholds:
      < 24 hours      -> +20 (critical, same-day)
      24-47 hours (1d) -> +15
      48-71 hours (2d) -> +5
      72+ hours (3d+)  -> +0
    """
    if min_recovery_hours < 24:
        return 20
    if min_recovery_hours < 48:
        return 15
    if min_recovery_hours < 72:
        return 5
    return 0


def _count_home_away(fixtures: list, team_id: str = "") -> tuple:
    """Return (home_count, away_count) for a list of fixtures.

    A match is home if team_id matches:
      - "home_team_id" field on the fixture, OR
      - "home_team.team_id" if home_team is a dict

    If team_id is empty, returns (0, 0).
    """
    if not team_id:
        return 0, 0
    home = 0
    away = 0
    for f in fixtures:
        h_team_id = f.get("home_team_id") or ""
        if not h_team_id and isinstance(f.get("home_team"), dict):
            h_team_id = f["home_team"].get("team_id") or f["home_team"].get("id") or ""
        if str(h_team_id) == str(team_id):
            home += 1
        else:
            away += 1
    return home, away


def _travel_penalty_for_transitions(sides: List[str]) -> tuple:
    """Travel/logistics penalty per transition between consecutive matches.

    Jul 29 2026 v6 — User spec:
      Home -> Home  +0 (ideal, no travel)
      Home -> Away  +2 (team leaves home for away)
      Away -> Home  +1 (returning home, then can recover)
      Away -> Away  +3 (two consecutive away matches)

    Total travel penalty is capped at MAX_TRAVEL_PENALTY (default 10)
    so logistics can't dominate the load-based score.

    Returns (penalty, transitions) where transitions is a list
    of strings like ["H->A", "A->A", ...] for UI rendering.
    """
    if not sides or len(sides) < 2:
        return 0, []

    _TRAVEL_DELTA = {
        ("home", "home"): 0,
        ("home", "away"): 2,
        ("away", "home"): 1,
        ("away", "away"): 3,
    }

    transitions = []
    total = 0
    for prev, nxt in zip(sides, sides[1:]):
        delta = _TRAVEL_DELTA.get((prev, nxt), 0)
        total += delta
        # Compact notation: "H->A", "A->H", etc.
        arrow = f"{prev[0].upper()}->{nxt[0].upper()}"
        transitions.append(arrow)

    return min(total, MAX_TRAVEL_PENALTY), transitions


def compute_fixture_congestion(fixtures: list, team_id: str = "") -> dict:
    """Compute Fixture Congestion score from a list of fixtures.

    Each fixture dict is expected to have either:
      - "timestamp": unix epoch seconds
    OR
      - "date" + "time": "dd/mm" + "HH:MM"

    If team_id is passed, also counts home/away matches.
    A match is home if home_team_id == team_id (or
    home_team.team_id == team_id). Otherwise: away.

    Returns a dict suitable for caching in the team live_cache.

    Schema (Jul 29 2026 v5):
        {
          "fixture_congestion": 90,
          "status": "EXTREME",
          "average_recovery_days": 1.8,
          "minimum_recovery_days": 1,
          "minimum_recovery_hours": 5,
          "next_matches_count": 5,
          "recovery_intervals": [2, 2, 1, 2],
          "home_matches": 3,
          "away_matches": 2,
          "total_matches": 5
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
        home_count, away_count = _count_home_away(fixtures, team_id)
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_recovery_days": 0.0,
            "minimum_recovery_days": 0,
            "minimum_recovery_hours": 0,
            "next_matches_count": len(parsed),
            "recovery_intervals": [],
            "recovery_hours": [],
            "home_matches": home_count,
            "away_matches": away_count,
            "total_matches": len(fixtures),
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
        # Single match — no recovery intervals, but still count home/away.
        home_count, away_count = _count_home_away(fixtures, team_id)
        return {
            "fixture_congestion": 0,
            "status": "LOW",
            "average_recovery_days": 0.0,
            "minimum_recovery_days": 0,
            "minimum_recovery_hours": 0,
            "next_matches_count": len(parsed),
            "recovery_intervals": [],
            "recovery_hours": [],
            "home_matches": home_count,
            "away_matches": away_count,
            "total_matches": len(fixtures),
        }

    avg_recovery = sum(intervals) / len(intervals)

    # Find minimum recovery, both in hours (raw) and days (float).
    min_recovery_days = min(intervals)
    min_recovery_hours = min(interval_hours) if interval_hours else 0.0

    # Penalty uses HOURS (v4) so same-day 1-hour gap -> +20 critical.
    penalty = _penalty_for_min_rest_hours(min_recovery_hours)

    # Load points use round(days) (0.9 -> 1 day -> 90 pts; 0.04 -> 0 d -> 100 pts).
    load_points = [_rest_to_load_points(round(r)) for r in intervals]
    average_load = sum(load_points) / len(load_points)

    fc_raw = average_load + penalty
    fc = max(0, min(100, int(round(fc_raw))))

    home_count, away_count = _count_home_away(fixtures, team_id)

    # Travel penalty (v6): sum of H->A / A->H / A->A / H->H transitions,
    # capped at MAX_TRAVEL_PENALTY (=10). Applied on top of base FC.
    sides: List[str] = []
    for f in fixtures:
        h_team_id = f.get("home_team_id") or ""
        if not h_team_id and isinstance(f.get("home_team"), dict):
            h_team_id = f["home_team"].get("team_id") or f["home_team"].get("id") or ""
        sides.append("home" if str(h_team_id) == str(team_id) else "away")

    travel_penalty, travel_transitions = _travel_penalty_for_transitions(sides)

    fc_raw_with_travel = fc + travel_penalty
    fc_final = max(0, min(100, int(round(fc_raw_with_travel))))

    return {
        "fixture_congestion": fc_final,
        "status": _status_for(fc_final),
        "average_recovery_days": round(avg_recovery, 1),
        "minimum_recovery_days": min_recovery_days,
        "minimum_recovery_hours": min_recovery_hours,
        "next_matches_count": len(parsed),
        "recovery_intervals": intervals,
        "recovery_hours": interval_hours,
        "home_matches": home_count,
        "away_matches": away_count,
        "total_matches": len(fixtures),
        "travel_penalty": travel_penalty,
        "travel_transitions": travel_transitions,
    }


def progress_bar(fc: int, width: int = 10) -> str:
    """Render a unicode progress bar for the FC value (block characters)."""
    fc = max(0, min(100, int(fc)))
    filled = round(fc / 10)
    if filled > width:
        filled = width
    return "\u2588" * filled + "\u2591" * (width - filled)


def risk_label(fc: int) -> str:
    """Return just the level (Low/Medium/High/Very High).

    Frontend prepends "Rotation Risk — " automatically.
    New thresholds (Jul 29 2026, user spec):
      0-30   -> Low
      31-55  -> Medium
      56-80  -> High
      81-100 -> Very High
    """
    if fc <= 30:
        return "Low"
    if fc <= 55:
        return "Medium"
    if fc <= 80:
        return "High"
    return "Very High"

