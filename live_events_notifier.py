"""live_events_notifier.py — Sep 19 2026

Polls /lineup_ai/api/live_events every 60s and forwards each NEW
red_card / substitution event (already filtered for minute<=35 by the
mirror bot) to the @lineupvalue_alert Telegram channel as a single
formatted message in the same compact form as the channel examples:

    Hapoel Beer Sheva - Dinamo Zagreb
    🔁 23 min — 🟠 L. Kacavenda (Dinamo Zagreb)

    Deportivo La Coruna - Sevilla
    🟥 59 min — Angeliño (Deportivo La Coruna)

The mirror bot (/home/openclaw/telegram-mirror/bot.py) writes events
into LV's live_events SQLite table when @footylivebot posts them;
this notifier picks them up from there and reposts them in our
main channel. The @lineupvalue_live channel is untouched — we
duplicate, not redirect.

State: data/live_events_notifier_state.json — {event_id: epoch_seen}.
First run: marks current backlog as seen without posting any of it,
so a long downtime doesn't flood the channel with stale events.
After that, only new events are forwarded.

Run: python3 live_events_notifier.py
Restart: bash /home/openclaw/FormAlert/start_live_events_notifier.sh
(or xi_supervisor.sh covers it on cron).

Env:
  SXI_TG_TOKEN     — Telegram bot token (same one as the other notifiers)
  SXI_TG_CHAT      — target channel, default @lineupvalue_alert
  LIVE_FEED_URL    — LV endpoint, default http://127.0.0.1:8099/lineup_ai/api/live_events
  INTERVAL_SEC     — poll period, default 60
  BACKFILL_HOURS   — on first run only, treat events newer than this as
                     "fresh"; older ones are pre-loaded as already seen.
                     Default 0 (= suppress everything that's already in the
                     table when we first boot, just like the tweets notifier).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = "/home/openclaw/FormAlert"
LOG_PATH = os.path.join(APP_DIR, "data", "live_events_notifier.log")
STATE_PATH = os.path.join(APP_DIR, "data", "live_events_notifier_state.json")

LIVE_FEED_URL = os.environ.get(
    "LIVE_FEED_URL", "http://127.0.0.1:8099/lineup_ai/api/live_events"
)
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "60"))
BACKFILL_HOURS = float(os.environ.get("BACKFILL_HOURS", "0"))

# Telegram target. Reuse the same env-prefix as other notifiers so cron
# only needs to declare tokens once.
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", ""),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT",
    os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert"),
)

# ----- markdown cleanup -----------------------------------------------------

_MD_BOLD = re.compile(r"\*+")
_EMOJI_SOCCER = "\u26bd"  # soccer ball, appears in some match labels
_EMOJI_RED = "\U0001F7E5"
_EMOJI_SUB = "\U0001F501"

# Suffixes that appear at the end of European club names and have to be
# stripped before name-based lookup, otherwise "Atletico" and
# "Atletico Madrid" don't collide. Mirrors the JS _normTeamName() that
# the team-sidebar footer-link feature uses on lineup_team_view.py.
_TEAM_SUFFIX_RE = re.compile(
    r"\s*(?:FC|CF|SC|AFC|CFC|SSC|AS|RC|BC|CD|SAD|SL|SD)$",
    re.IGNORECASE,
)

# Diacritic folding table for NFD-decompose + strip combining marks.
def _fold_diacritics(s: str) -> str:
    import unicodedata as _u
    return "".join(c for c in _u.normalize("NFD", s) if _u.category(c) != "Mn")


def _norm_team(s: str) -> str:
    """Lowercase + strip non-alphanumeric + drop common European suffixes.

    Matches the JS helper from lineup_team_view.py so behaviour stays
    consistent between web sidebar and this Telegram channel."""
    if not s:
        return ""
    folded = _fold_diacritics(s).lower().strip()
    folded = _TEAM_SUFFIX_RE.sub("", folded).strip()
    return re.sub(r"[^a-z0-9]", "", folded)


# ----- team index -----------------------------------------------------------

LV_BASE = os.environ.get("LV_BASE", "https://x11radar.ru")
TEAMS_JSON_URL = f"{LV_BASE}/lineup_ai/data.json"
TEAM_INDEX_PATH = os.path.join(APP_DIR, "data", "live_events_team_index.json")
TEAM_ALIASES_PATH = os.path.join(APP_DIR, "data", "team_name_aliases.json")
TEAM_INDEX_TTL = int(os.environ.get("TEAM_INDEX_TTL", "3600"))

_team_index: dict[str, dict] = {}
_team_index_loaded_at: float = 0.0


def _flatten_teams(node, out):
    """Recursively walk /lineup_ai/data.json which is a 3-level
    Country -> League -> [team] structure and yield every team dict."""
    if isinstance(node, dict):
        for v in node.values():
            _flatten_teams(v, out)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, dict) and "id" in v and "name" in v:
                out.append(v)
            else:
                _flatten_teams(v, out)


def _load_alias_map() -> dict[str, dict]:
    """Build {normalized_alias: {id, name}} from data/team_name_aliases.json.

    Each entry in that file is keyed by LV team_id and carries
    .aliases = [rotowire_seen + manual additions]. Used as fallback
    after _flatten_teams() because LV does not contain LaLiga clubs
    but the alias file does (e.g. Dinamo Zagreb -> '8G5ufQTg')."""
    if not os.path.exists(TEAM_ALIASES_PATH):
        return {}
    try:
        with open(TEAM_ALIASES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        log(f"  alias file load failed: {type(exc).__name__}: {exc}")
        return {}
    out: dict[str, dict] = {}
    for tid, info in data.items():
        if not isinstance(info, dict):
            continue
        canonical_name = info.get("name") or ""
        if not canonical_name:
            continue
        canonical = {"id": tid, "name": canonical_name}
        # Index the canonical name AND every alias
        out[_norm_team(canonical_name)] = canonical
        for alias in info.get("aliases", []) or []:
            if not alias:
                continue
            nk = _norm_team(alias)
            if nk and nk not in out:
                out[nk] = canonical
    return out


def _build_team_index() -> dict[str, dict]:
    """Fetch /lineup_ai/data.json + team_name_aliases.json, build
    {normalized_name: {id, name}}.

    Cache to disk (TEAM_INDEX_PATH) and in memory (TEAM_INDEX_TTL seconds)
    so we don't hammer LV on every poll cycle."""
    global _team_index, _team_index_loaded_at
    now = time.time()
    if _team_index and (now - _team_index_loaded_at) < TEAM_INDEX_TTL:
        return _team_index

    teams_out: list[dict] = []
    try:
        with urllib.request.urlopen(TEAMS_JSON_URL, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        _flatten_teams(data, teams_out)
        index = {_norm_team(t["name"]): {"id": t["id"], "name": t["name"]}
                 for t in teams_out if t.get("id") and t.get("name")}
    except Exception as exc:
        log(f"team index build failed: {type(exc).__name__}: {exc}")
        # Fall back to disk cache if available.
        if os.path.exists(TEAM_INDEX_PATH):
            try:
                with open(TEAM_INDEX_PATH, "r", encoding="utf-8") as fh:
                    cached = json.load(fh)
                teams_out = cached.get("teams") or []
                index = {_norm_team(t["name"]): {"id": t["id"], "name": t["name"]}
                         for t in teams_out if t.get("id") and t.get("name")}
            except Exception as exc2:
                log(f"  disk cache fallback also failed: {exc2}")
                index = {}
        else:
            index = {}

    # Augment with team_name_aliases.json so UEFA/CL clubs like
    # "Dinamo Zagreb" / "Hapoel Beer Sheva" (not in leagues_data)
    # can still resolve via their rotowire_seen aliases.
    alias_index = _load_alias_map()
    if alias_index:
        for k, v in alias_index.items():
            if k and k not in index:
                index[k] = v
        log(f"  team index: {len(alias_index)} alias entries merged")

    _team_index = index
    _team_index_loaded_at = now
    try:
        with open(TEAM_INDEX_PATH, "w", encoding="utf-8") as fh:
            json.dump({"loaded_at": now, "teams": teams_out}, fh)
    except Exception:
        pass
    log(f"  team index rebuilt: {len(index)} entries")
    return index


def _resolve_team(name: str) -> dict | None:
    if not name:
        return None
    idx = _team_index or _build_team_index()
    return idx.get(_norm_team(name))


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def log(msg: str) -> None:
    ts = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:
        print(f"log write failed: {exc}", file=sys.stderr)
    print(line, flush=True)


def strip_md(s: str) -> str:
    """Strip **bold** and trim surrounding whitespace. Channels don't
    render markdown well in plain sendMessage calls."""
    if not s:
        return ""
    s = _MD_BOLD.sub("", s)
    s = s.replace(_EMOJI_SOCCER, "").strip()
    # Trailing colon / dash kept off the end so format is clean
    s = s.rstrip(":").strip()
    return s


def fmt_event(ev: dict) -> tuple[str, str]:
    """Render one event as (plain_text, html_text).

    Two flavours so callers can pick the right parse_mode without
    re-running the formatter. The HTML variant:
      - wraps the parenthesised team in <a href> when resolvable
      - adds a footer link on a new line, e.g. "Espanyol ↗",
        matching the per-tweet footer pattern from
        lineup_team_view.py (commit 4f9800e).

    The plain-text variant renders the footer as "[Team ↗]" for
    channels / clients that don't render HTML.
    """
    et = ev.get("event_type") or ""
    label = strip_md(ev.get("match_label") or "")
    player = strip_md(ev.get("player") or "")
    team = strip_md(ev.get("team") or "")
    minute = int(ev.get("minute") or 0)

    if et == "red_card":
        icon = _EMOJI_RED
    elif et == "substitution":
        icon = _EMOJI_SUB
    else:
        icon = "\u2022"

    head_plain = f"{icon} {minute} min \u2014 {player}"
    head_html = head_plain
    resolved = None
    if team:
        resolved = _resolve_team(team)
        head_plain += f" ({team})"
        if resolved:
            url = f"{LV_BASE}/lineup_ai/{resolved['id']}"
            head_html += f' (<a href="{_html_escape(url)}">{_html_escape(team)}</a>)'
        else:
            head_html += f" ({_html_escape(team)})"

    # Build footer link (matches team-page tweet footer pattern).
    footer_plain = ""
    footer_html = ""
    if resolved:
        url = f"{LV_BASE}/lineup_ai/{resolved['id']}"
        footer_plain = f"\n{team} \u2197"
        footer_html = f'\n<a href="{_html_escape(url)}">{_html_escape(team)} \u2197</a>'

    if label:
        return (
            f"{label}\n{head_plain}{footer_plain}",
            f"{_html_escape(label)}\n{head_html}{footer_html}",
        )
    return (f"{head_plain}{footer_plain}", f"{head_html}{footer_html}")


# ----- feed ------------------------------------------------------------------


def fetch_events() -> list[dict]:
    url = LIVE_FEED_URL + ("?limit=20" if "?" not in LIVE_FEED_URL else "&limit=20")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        log(f"feed fetch failed: {exc}")
        return []
    except Exception as exc:
        log(f"feed unexpected: {type(exc).__name__}: {exc}")
        return []
    return data.get("events") or []


# ----- state -----------------------------------------------------------------


def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"seen": {}, "initialized": False}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"seen": {}, "initialized": False}


def save_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception as exc:
        log(f"state save failed: {exc}")


# ----- telegram --------------------------------------------------------------


def send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    """sendMessage. parse_mode "HTML" enables <a href> rendering;
    Telegram will reject messages with unbalanced tags so the caller
    must pass pre-sanitised text."""
    if not TG_TOKEN or not TG_CHAT:
        log("telegram token or chat not configured; skipping send")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        if '"ok":true' in body or '"ok": true' in body:
            return True
        log(f"send returned non-ok body: {body[:200]}")
        return False
    except Exception as exc:
        log(f"send failed: {type(exc).__name__}: {exc}")
        return False


# ----- main loop -------------------------------------------------------------


def main() -> None:
    log(f"=== live_events_notifier starting ===")
    log(f"  FEED_URL={LIVE_FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    log(f"  STATE_PATH={STATE_PATH}")

    state = load_state()
    seen: dict = state.get("seen", {})
    initialized: bool = bool(state.get("initialized"))

    backfill_cutoff = None
    if not initialized:
        if BACKFILL_HOURS > 0:
            backfill_cutoff = time.time() - BACKFILL_HOURS * 3600
            log(f"first run: BACKFILL_HOURS={BACKFILL_HOURS}; will pre-mark events older than that as seen")
        else:
            log(f"first run: BACKFILL_HOURS=0; will pre-mark ALL existing events as seen (silent boot)")

    while True:
        try:
            events = fetch_events()
            now = time.time()
            sent = 0
            for ev in events:
                eid = ev.get("event_id") or ""
                if not eid:
                    continue
                if eid in seen:
                    continue
                # First-run: pre-mark as seen without sending anything.
                if not initialized:
                    if backfill_cutoff is None:
                        seen[eid] = now
                        continue
                    try:
                        ts = _dt.datetime.fromisoformat(ev["created_at"].rstrip("Z")).timestamp()
                    except Exception:
                        ts = 0
                    if ts < backfill_cutoff:
                        seen[eid] = now
                        continue
                    # Inside backfill window: still suppress on first run
                    seen[eid] = now
                    continue
                # Live: render and send. Telegram's HTML parse_mode
                # is strict — if any team or label contains an unbalanced
                # tag, the message gets a 400 and we should fall back to
                # plain text so we never silently drop an event.
                plain_text, html_text = fmt_event(ev)
                if send_telegram(html_text, parse_mode="HTML"):
                    seen[eid] = now
                    sent += 1
                elif send_telegram(plain_text, parse_mode=""):
                    seen[eid] = now
                    sent += 1
                    log(f"  sent {eid} as plain text (HTML parse failed)")
            if not initialized and events:
                log(f"  first-run primed: {len(events)} events pre-marked as seen")
                state["initialized"] = True
                initialized = True
                save_state(state)
            elif sent:
                log(f"  cycle: events={len(events)} sent={sent} state={len(seen)}")
                # Persist the dedup map on every successful send so
                # a process restart does not resend already-delivered
                # events. Without this save_state call, the in-memory
                # `seen` dict and the on-disk state diverge: after a
                # restart every "seen" event would look new again and
                # flood the TG channel with duplicates.
                save_state(state)
        except Exception as exc:
            log(f"loop error: {type(exc).__name__}: {exc}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
