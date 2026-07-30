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

from datetime import datetime, timedelta
from typing import List

# Map: rest_days -> points (anything >= 5 -> 0 points)
# Map: recovery_hours (raw interval, NOT days) -> load points.
# Jul 29 2026 v7 — User spec: hours-based to avoid
# "прыжок" at boundaries like 71h vs 72h.
# Range -> load:
#   <24       -> 100 (critical, same-day)
#   24-47     -> 90
#   48-71     -> 70
#   72-95     -> 40
#   96-119    -> 20
#   120+      -> 0 (plenty of rest)
_LOAD_BY_REST_HOURS = [
    (24,  100),  # <24h -> 100
    (48,  90),   # 24-47h -> 90
    (72,  70),   # 48-71h -> 70
    (96,  40),   # 72-95h -> 40
    (120, 20),   # 96-119h -> 20
]
_DEFAULT_LOAD = 0  # 120+ hours

# Maximum travel penalty applied on top of FC base.
# Caps total logistics bonus so a chain of A->A transitions
# cannot inflate FC beyond +10.
MAX_TRAVEL_PENALTY = 10


def _hours_to_load_points(hours: float) -> int:
    """Map recovery interval (HOURS, raw) to load points.

    Jul 29 2026 v7 — User spec. Continuous hour-based
    mapping avoids the round(days) boundary jumps
    (e.g. 71h and 72h being identical is fine, but
    47h and 48h jump from 70 to 40 with the old
    integer-day mapping).

    Buckets (lower-bound inclusive, upper-bound exclusive):
      hours < 24   -> 100 (critical)
      hours < 48   -> 90
      hours < 72   -> 70
      hours < 96   -> 40
      hours < 120  -> 20
      hours >= 120 -> 0 (5+ days)
    """
    if hours < 0:
        return _LOAD_BY_REST_HOURS[0][1]
    for upper_bound, points in _LOAD_BY_REST_HOURS:
        if hours < upper_bound:
            return points
    return _DEFAULT_LOAD


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

    Jul 30 2026 v8 (user spec): the previous thresholds
    (+20 / +15 / +5 / +0) doubled the load on the
    shortest intervals because the load_points map
    ALREADY assigns 100 points to <24h. Penalty is now
    an emergency-only amplifier, not a duplicate of the
    same "very little rest" signal.

    New thresholds:
      < 24 hours     -> +10 (still emergency, but no
                          longer stacking 100+20=120)
      24-47 hours    -> +5
      48+ hours      -> +0 (load_points alone is enough)

    Example:
      23h interval -> load=100, penalty=+10 -> FC=110
      -> clamp(110) = 100 (max).

    The clamp at the call site prevents the score from
    exceeding 100 even with travel_penalty on top.
    """
    if min_recovery_hours < 24:
        return 10
    if min_recovery_hours < 48:
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



def calculate_next_14_days_density(fixtures: list) -> dict:
    """Count how many fixtures fall within the next 14 days.

    Jul 30 2026 (user spec): uses ONLY fixtures[:5] - no
    additional API calls. Returns count and density grade.

    Thresholds:
      0-1 matches -> NORMAL
      2 matches   -> NORMAL
      3 matches   -> MODERATE
      4 matches   -> HIGH
      5 matches   -> EXTREME

    Returns:
        {
          "next_14_days_matches": int (0..5),
          "period_days": 14,
          "density_status": "NORMAL" | "MODERATE" | "HIGH" | "EXTREME"
        }
    """
    if not fixtures:
        return {
            "next_14_days_matches": 0,
            "period_days": 14,
            "density_status": "NORMAL",
        }

    current_time = datetime.utcnow()
    period_end = current_time + timedelta(days=14)

    # Parse fixtures to datetime (reuse logic without rebuilding)
    count = 0
    for f in fixtures[:5]:
        ts = f.get("timestamp")
        dt = None
        if ts:
            try:
                dt = datetime.utcfromtimestamp(int(ts))
            except (TypeError, ValueError, OSError):
                dt = None
        if dt is None:
            date_str = (f.get("date") or "").strip()
            time_str = (f.get("time") or "").strip()
            if not date_str:
                continue
            try:
                parts = date_str.split("/")
                day_i, month_i = int(parts[0]), int(parts[1])
                now = datetime.utcnow()
                year_i = now.year
                candidate = datetime(year_i, month_i, day_i, 12, 0)
                if candidate < now:
                    candidate = datetime(year_i + 1, month_i, day_i, 12, 0)
                if time_str and ":" in time_str:
                    h, m = time_str.split(":")[:2]
                    candidate = candidate.replace(
                        hour=int(h), minute=int(m)
                    )
                dt = candidate
            except (ValueError, IndexError):
                continue
        if dt is None:
            continue
        if current_time <= dt <= period_end:
            count += 1

    # Density status
    if count <= 2:
        density_status = "NORMAL"
    elif count == 3:
        density_status = "MODERATE"
    elif count == 4:
        density_status = "HIGH"
    else:
        density_status = "EXTREME"

    return {
        "next_14_days_matches": count,
        "period_days": 14,
        "density_status": density_status,
    }


def _next_14_days_penalty(count: int) -> int:
    """Penalty applied on top of FC for matches in next 14 days.

    Jul 30 2026 (user spec):
      0-2 matches -> +0
      3 matches   -> +5
      4 matches   -> +10
      5 matches   -> +15
    """
    if count >= 5:
        return 15
    if count == 4:
        return 10
    if count == 3:
        return 5
    return 0


def _rotation_risk(fc: float) -> str:
    """Return text risk level for FC value.

    Jul 30 2026 (user spec):
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

    # Load points use RAW HOURS (v7). No round(days) — buckets are
    # continuous in hours so 47.9h -> 90 pts and 48.0h -> 70 pts
    # (no 71h vs 72h boundary artifact).
    load_points = [_hours_to_load_points(h) for h in interval_hours]
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

    # Jul 30 2026 (user spec): Next 14 Days density metric.
    # Uses ONLY fixtures[:5] - no additional API calls.
    next_14 = calculate_next_14_days_density(fixtures)
    next_14_days_penalty = _next_14_days_penalty(next_14["next_14_days_matches"])

    fc_raw_with_travel = fc + travel_penalty
    fc_raw_with_density = fc_raw_with_travel + next_14_days_penalty
    fc_final = max(0, min(100, int(round(fc_raw_with_density))))

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
        "next_14_days_matches": next_14["next_14_days_matches"],
        "next_14_days_period": next_14["period_days"],
        "next_14_days_density_status": next_14["density_status"],
        "next_14_days_penalty": next_14_days_penalty,
        "rotation_risk": _rotation_risk(fc_final),
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

