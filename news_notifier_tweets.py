"""
news_notifier_tweets.py — Sep 13 2026
Polls the local FormAlert /lineup_ai/api/recent_tweets endpoint every
60s and forwards each new tweet to the LineupValue Telegram channel
@lineupvalue_alert as a single, separate message — verbatim, no
wrapping, no splitting, no Read More link.

The endpoint already filters by keyword / blacklist / AI relevance /
dedup, so we forward every new tweet without re-filtering.

State: data/news_state_tweets.json — {tweet_id: epoch_seen}.
On the first run, current tweets are marked as seen (no backfill dump)
so the channel isn't flooded with stale content.

Run: python3 news_notifier_tweets.py
Restart: bash /home/openclaw/FormAlert/start_news_notifier_tweets.sh
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# === Config ===
FEED_URL = os.environ.get(
    "NEWS_TWEETS_FEED_URL",
    "http://localhost:8099/lineup_ai/api/recent_tweets?limit=20",
)
TG_TOKEN = os.environ.get(
    "NEWS_TG_TOKEN",
    os.environ.get("SXI_TG_TOKEN", "8804020090:AAFz9o8bMMwzMNzK3Kr7cEe_dUVxAzo9Y44"),
)
TG_CHAT = os.environ.get(
    "NEWS_TG_CHAT", os.environ.get("SXI_TG_CHAT", "@lineupvalue_alert")
)
INTERVAL_SEC = int(os.environ.get("NEWS_TWEETS_INTERVAL_SEC", "60"))

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state_tweets.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_tweets.log"

_HTML_TAG = re.compile(r"<[^>]+>")


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    if not STATE_PATH.exists():
        return {"seen": {}}
    try:
        return json.loads(STATE_PATH.read_text("utf-8") or "{}")
    except Exception:
        return {"seen": {}}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "news_notifier_tweets/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def normalize_text(text):
    """Collapse runs of whitespace inside a line but keep newlines so the
    tweet text stays readable in the channel exactly as published."""
    if not text:
        return ""
    from html import unescape
    s = _HTML_TAG.sub(" ", text)
    s = unescape(s)
    # Collapse horizontal whitespace, keep newlines
    s = re.sub(r"[^\S\n]+", " ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    return s.strip()


def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    params = {
        "chat_id": TG_CHAT,
        "text": text,
        "disable_web_page_preview": "true",
    }
    data = urllib.parse.urlencode(params, quote_via=urllib.parse.quote).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
        return '"ok":true' in body
    except Exception as e:
        log(f"  telegram send failed: {e}")
        return False


def process_once(state):
    try:
        payload = fetch(FEED_URL)
    except Exception as e:
        log(f"  fetch failed: {e}")
        return 0

    tweets = payload.get("tweets") or []
    seen = state.get("seen") or {}
    is_first_run = not state.get("initialized", False)

    if is_first_run:
        # Mark all current tweets as seen without sending (no backfill)
        for t in tweets:
            seen[t.get("tweet_id")] = int(time.time())
        state["seen"] = seen
        state["initialized"] = True
        save_state(state)
        log(f"  first run: seeded {len(seen)} tweets; no notifications sent")
        return 0

    sent = 0
    for t in tweets:
        tid = t.get("tweet_id")
        if not tid or tid in seen:
            continue
        # Forward the tweet verbatim as a single Telegram message.
        text = normalize_text(t.get("text") or "")
        if not text:
            seen[tid] = int(time.time())
            continue
        ok = send_telegram_text(text)
        if ok:
            sent += 1
            seen[tid] = int(time.time())
            log(f"  SENT tid={tid} text={text[:80]!r}")
        else:
            log(f"  send failed for tid={tid}, will retry")
            break

    # Trim seen to last 2000 ids
    if len(seen) > 2000:
        keep = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:2000]
        seen = dict(keep)
    state["seen"] = seen
    save_state(state)
    log(f"  cycle: tweets_now={len(tweets)} new_sent={sent} state_size={len(seen)}")
    return sent


def main():
    log("=== news_notifier_tweets (FormAlert recent_tweets sidebar) starting ===")
    log(f"  FEED_URL={FEED_URL}  TG_CHAT={TG_CHAT}  INTERVAL={INTERVAL_SEC}s")
    state = load_state()
    log(f"  loaded state: {len(state.get('seen') or {})} seen tweet_ids")

    while True:
        try:
            n = process_once(state)
            if n == 0:
                pass
        except Exception as e:
            log(f"  cycle error: {e!r}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
