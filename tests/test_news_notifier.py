"""Unit tests for news_notifier — no real Telegram, no real network."""
import sys
sys.path.insert(0, '/home/openclaw/FormAlert')
import news_notifier as n

PASS = 0
FAIL = 0
FAILURES = []


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


def check_contains(label, haystack, needle):
    global PASS, FAIL
    if needle.lower() in haystack.lower():
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{label}: {needle!r} not in {haystack!r}")


def check_not_contains(label, haystack, needle):
    global PASS, FAIL
    if needle.lower() not in haystack.lower():
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{label}: {needle!r} FOUND in {haystack!r}")


# --- strip_rotowire ---
check("strip empty",          n.strip_rotowire(""), "")
check("strip no roto",        n.strip_rotowire("Hello world"), "Hello world")
check("strip Rotowire",       n.strip_rotowire("Visit Rotowire for more"), "Visit for more")
check("strip rotowire lower", n.strip_rotowire("rotowire.com is the source"), ".com is the source")
check("strip ROTOWIRE upper", n.strip_rotowire("ROTOWIRE ALL CAPS"), "ALL CAPS")
check("strip mid-sentence",   n.strip_rotowire("Per Rotowire, Gakpo is out"),
      "Per, Gakpo is out")
check("strip multi",          n.strip_rotowire("Rotowire says rotowire.com foo"),
      "says.com foo")

# --- clean_html ---
check("clean plain",          n.clean_html("plain text"), "plain text")
check("clean with tags",      n.clean_html("<p>hello</p> <b>world</b>"),
      "hello world")
check("clean with entities",  n.clean_html("&amp; &lt; &gt;"), "& < >")
check("clean multi-space",    n.clean_html("a   b\n\nc"), "a b c")

# --- strip_cta (boilerplate) ---
check("cta: visit.com for more",
      n.strip_cta('Coach said "injury is minor." Visit.com for more analysis on this update.'),
      'Coach said "injury is minor.".')
check("cta: read more at",
      n.strip_cta('Coach said "fit." Read more at ESPN.com for the full story.'),
      'Coach said "fit.".')
check("cta: continue reading",
      n.strip_cta('He scored twice. Continue reading on BBC.com for more coverage.'),
      'He scored twice.')
check("cta: for the full report",
      n.strip_cta('Injury update. For the full report, click here.'),
      'Injury update.')
check("cta: no cta to strip",
      n.strip_cta('Coach said "all good."'),
      'Coach said "all good."')
check("cta: trailing whitespace",
      n.strip_cta('"He is fit."    '),
      '"He is fit."')
check("cta: visit rotowire.com",
      n.strip_cta('Coach said. Visit rotowire.com for more analysis on this update.'),
      'Coach said.')

# --- truncate ---
check("truncate short",       n.truncate("hello", 100), "hello")
check("truncate at sentence", n.truncate("Hello. World. Done.", 14), "Hello. World.…")
check("truncate at word",     n.truncate("averylongword here", 5), "avery…")
check("truncate with end",    n.truncate("no sentence end", 8), "no…")

# --- _shorten_url ---
check("short player url",
      n._shorten_url("https://www.rotowire.com/soccer/player/cody-gakpo-26727"),
      "player/cody-gakpo-26727")
check("short no path",        n._shorten_url("https://www.rotowire.com"), "https://www.rotowire.com")
check("short non-soccer",     n._shorten_url("https://example.com/x/y"), "x/y")
check("short relative path",  n._shorten_url("https://rotowire.com/soccer/news/123"),
      "news/123")

# --- build_message ---
item = {
    "guid": "test1",
    "title": "Cody Gakpo: Uncertain for Fulham clash",
    "link": "https://www.rotowire.com/soccer/player/cody-gakpo-26727",
    "body": "Gakpo (adductor) remains uncertain for Saturday's Premier League clash.",
    "pub_raw": "",
    "pub_ts": 0,
}
msg = n.build_message(item)
check_contains("msg has title",       msg, "Cody Gakpo")
check_contains("msg has 📰",          msg, "📰")
check_contains("msg has body",        msg, "Gakpo")
check_not_contains("msg NO link",     msg, "cody-gakpo-26727")
check_not_contains("msg NO 🔗 line",  msg, "🔗")
check_not_contains("msg NO player/",  msg, "player/")
check_not_contains("msg no rotowire", msg, "rotowire")

# Item with rotowire in body
item2 = {
    "guid": "test2",
    "title": "Some news about Player",
    "link": "https://rotowire.com/soccer/player/test",
    "body": "Visit Rotowire.com for more analysis. RotoWire says foo.",
    "pub_raw": "",
    "pub_ts": 0,
}
msg2 = n.build_message(item2)
check_not_contains("msg2 no rotowire", msg2, "rotowire")
check_not_contains("msg2 no Rotowire", msg2, "Rotowire")
check_not_contains("msg2 no ROTOWIRE", msg2, "ROTOWIRE")
check_not_contains("msg2 no rotoWire", msg2, "rotoWire")

# Item with rotowire in title
item3 = {
    "guid": "test3",
    "title": "Rotowire says Player is OUT",
    "link": "https://www.rotowire.com/x",
    "body": "Body text",
    "pub_raw": "",
    "pub_ts": 0,
}
msg3 = n.build_message(item3)
check_contains("msg3 has Player",    msg3, "Player")
check_not_contains("msg3 no rotowire", msg3, "rotowire")

# --- process() backfill / dedup (stubbed fetch + send) ---
# Monkey-patch
import news_notifier as N
SENT_CALLS = []
def fake_send(text):
    SENT_CALLS.append(text)
    return True
N.send_telegram = fake_send

FAKE_ITEMS = [
    {"guid": "g1", "title": "Old news 1", "link": "https://x.com/a", "body": "a", "pub_ts": 0, "pub_raw": ""},
    {"guid": "g2", "title": "Old news 2", "link": "https://x.com/b", "body": "b", "pub_ts": 0, "pub_raw": ""},
    {"guid": "g3", "title": "New news 1",  "link": "https://x.com/c", "body": "c", "pub_ts": 99999999999, "pub_raw": ""},
    {"guid": "g4", "title": "New news 2",  "link": "https://x.com/d", "body": "d", "pub_ts": 99999999999, "pub_raw": ""},
]
N.fetch_feed = lambda url: FAKE_ITEMS
import os, json, tempfile
tmpdir = tempfile.mkdtemp()
N.STATE_PATH = __import__("pathlib").Path(tmpdir) / "state.json"

# First run: all "new" (future ts) sent, "old" skipped & marked seen
SENT_CALLS.clear()
N.process()
check("first run sent 2",  len(SENT_CALLS), 2)
check("first run state",   N.STATE_PATH.exists(), True)

# Second run: nothing new (all seen)
SENT_CALLS.clear()
N.process()
check("second run sent 0", len(SENT_CALLS), 0)

# Add a new item, re-run
FAKE_ITEMS.append({"guid": "g5", "title": "Newer", "link": "https://x.com/e",
                   "body": "e", "pub_ts": 99999999999, "pub_raw": ""})
SENT_CALLS.clear()
N.process()
check("third run sent 1",  len(SENT_CALLS), 1)
check("third run message", SENT_CALLS[0], "📰 Newer\ne")

# --- backfill rule: items older than BACKFILL_HOURS skipped but marked seen ---
# Reset state, use items with past pub_ts
N.STATE_PATH.unlink(missing_ok=True)
FAKE_BACKFILL = [
    {"guid": "old1", "title": "Ancient",  "link": "x", "body": "x", "pub_ts": 0, "pub_raw": ""},
    {"guid": "old2", "title": "Recent",   "link": "x", "body": "x",
     "pub_ts": int(__import__("time").time()) - 60, "pub_raw": ""},
]
N.fetch_feed = lambda url: FAKE_BACKFILL
SENT_CALLS.clear()
N.process()
check("backfill: only recent sent", len(SENT_CALLS), 1)
check("backfill: state has both",   len(json.loads(N.STATE_PATH.read_text())["seen"]), 2)

print(f"\n=== SUMMARY: {PASS} passed, {FAIL} failed ===")
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print(" ", f)
    sys.exit(1)
print("all news_notifier guards pass")
