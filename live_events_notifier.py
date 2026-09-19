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


def fmt_event(ev: dict) -> str:
    """Render one event as a single message ready for sendMessage."""
    et = ev.get("event_type") or ""
    label = strip_md(ev.get("match_label") or "")
    player = strip_md(ev.get("player") or "")
    team = strip_md(ev.get("team") or "")
    minute = int(ev.get("minute") or 0)

    if et == "red_card":
        icon = _EMOJI_RED
        verb = "Red Card"
    elif et == "substitution":
        icon = _EMOJI_SUB
        verb = "Sub"
    else:
        icon = "\u2022"
        verb = et or "Event"

    head = f"{icon} {minute} min — {player}"
    if team:
        head += f" ({team})"
    if label:
        return f"{label}\n{head}"
    return head


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


def send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        log("telegram token or chat not configured; skipping send")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        if '"ok":true' in body or '"ok": true' in body:
            return True
        log(f"send returned non-ok body: {body[:160]}")
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
                # Live: render and send
                text = fmt_event(ev)
                if send_telegram(text):
                    seen[eid] = now
                    sent += 1
            if not initialized and events:
                log(f"  first-run primed: {len(events)} events pre-marked as seen")
                state["initialized"] = True
                initialized = True
                save_state(state)
            elif sent:
                log(f"  cycle: events={len(events)} sent={sent} state={len(seen)}")
        except Exception as exc:
            log(f"loop error: {type(exc).__name__}: {exc}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
