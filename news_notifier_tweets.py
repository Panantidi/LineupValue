"""
news_notifier_tweets.py — Sep 13 2026
Polls the local FormAlert /lineup_ai/api/recent_tweets endpoint every
60s and forwards new context-relevant tweets to the LineupValue Telegram
channel @lineupvalue_alert.

The endpoint returns tweets that have already been filtered by the
FormAlert pipeline (keyword + blacklist + AI relevance + dedup), so we
do not filter again — we just forward.

Format mirrors the LaLiga / EPL / Bundesliga feeds:

  🐦 @FabrizioRomano

  <tweet text>

  <a href="https://x.com/i/web/status/<id>">Read More (URL)</a>

If the tweet has an image, we attach it via the Telegram sendPhoto
API call (single attachment, caption = tweet text).

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
HASHTAG = "#Tweets"

APP_DIR = Path(__file__).parent
STATE_PATH = APP_DIR / "data" / "news_state_tweets.json"
LOG_PATH = APP_DIR / "data" / "news_notifier_tweets.log"

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


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


def text_only(html_str):
    if not html_str:
        return ""
    s = _HTML_TAG.sub(" ", html_str)
    s = _WS.sub(" ", s).strip()
    return s


def build_message(tweet):
    """Compose a Telegram HTML message for a single tweet.

    Layout:
      🐦 <source_username>

      <tweet text>

      <a href="<url>">Read More (<url>)</a>
      #Tweets
    """
    author = tweet.get("source_username") or ""
    text = text_only(tweet.get("text") or "")
    url = tweet.get("url") or ""
    header = f"🐦 {html_escape(author) if author else 'Twitter'}"
    parts = [header, ""]
    if text:
        parts.append(html_escape(text))
    if url:
        parts.append("")
        parts.append(f'<a href="{html_escape(url)}">Read More ({html_escape(url)})</a>')
    parts.append(HASHTAG)
    return "\n".join(parts)


def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    params = {
        "chat_id": TG_CHAT,
        "text": text,
        "parse_mode": "HTML",
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


def send_telegram_photo(photo_url, caption, tweet_url):
    """Send a single photo with caption that contains a Read More link."""
    # Use sendPhoto; caption is plain text (no HTML) to keep it under 1024 chars
    caption_text = caption
    if tweet_url:
        caption_text = (caption_text + f"\n\n{tweet_url}\n{HASHTAG}").strip()
    if len(caption_text) > 1024:
        caption_text = caption_text[:1020] + "…"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    params = {
        "chat_id": TG_CHAT,
        "photo": photo_url,
        "caption": caption_text,
    }
    data = urllib.parse.urlencode(params, quote_via=urllib.parse.quote).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
        return '"ok":true' in body
    except Exception as e:
        log(f"  telegram photo send failed: {e}")
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
        # Build and send
        author = t.get("source_username") or ""
        text = text_only(t.get("text") or "")
        url = t.get("url") or ""
        media_url = t.get("media_url") or ""
        media_type = t.get("media_type") or ""

        if media_url and media_type in ("photo", ""):
            # Send as photo with caption (no HTML formatting)
            caption = f"🐦 {author}\n\n{text}" if author else text
            ok = send_telegram_photo(media_url, caption, url)
        else:
            msg = build_message(t)
            ok = send_telegram_text(msg)
        if ok:
            sent += 1
            seen[tid] = int(time.time())
            log(f"  SENT tid={tid} author={author!r} text={text[:80]!r}")
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
