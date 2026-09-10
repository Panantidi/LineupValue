"""Unit tests for sxi_notifier (no real Telegram)."""
import sys
sys.path.insert(0, "/home/openclaw/FormAlert")
import sxi_notifier as n
import time

PASS = 0
FAIL = 0
FAILURES = []


def check(label, got, expected):
    global PASS, FAIL
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append((label, got, expected))
        print(f"  FAIL: {label}: got {got!r}, expected {expected!r}")


# --- build_message ---
m_full = {
    "home_team": "Manchester United",
    "away_team": "Sabah FK",
    "home_id": "ppjDR086",
    "away_id": "fNGcxbyr",
    "kickoff_ts": 1789066800,
    "lv_time": "10.09 21:00",
    "_league_key": "ucl",
}
cfg = n.LEAGUES["ucl"]

# home-only
text = n.build_message(cfg, m_full, "home")
check("home-only has ✅ at start",  text.startswith("🏁 Starting XI\nEurope - Champions League\nDate - 10.09 (21:00)\n✅"), True)
check("home-only has no trailing ✅", "✅" not in text.split("(http")[1] or text.endswith(")") and "0)" in text, True)
check("home-only contains URL",     "https://x11radar.ru/lineup_ai/compare/ppjDR086" in text, True)
check("home-only has %20 (not +)",  "Manchester%20United" in text, True)
check("home-only has Sabah%20FK",   "Sabah%20FK" in text, True)

# away-only
m_away = dict(m_full)
m_away["sxi_home_confirmed"] = False
m_away["sxi_away_confirmed"] = True
text = n.build_message(cfg, m_away, "away")
check("away-only has trailing ✅",  text.rstrip().endswith(")✅"), True)

# both
m_both = dict(m_full)
m_both["sxi_home_confirmed"] = True
m_both["sxi_away_confirmed"] = True
text = n.build_message(cfg, m_both, "both")
check("both has leading ✅",        "\n✅ Manchester" in text, True)
check("both has trailing ✅",       text.rstrip().endswith(")✅"), True)

# URL contains all required params
url = n.make_url("ppjDR086", "fNGcxbyr", "Manchester United", "Sabah FK", "ucl", 1789066800)
for needle in ["mid=sx-ppjDR086-fNGcxbyr", "home_id=ppjDR086", "away_id=fNGcxbyr",
               "home_name=Manchester%20United", "away_name=Sabah%20FK",
               "rotowire_fran=1", "rw_league=ucl", "kickoff_ts=1789066800"]:
    check(f"URL has {needle!r}", needle in url, True)


# --- make_url edge cases ---
url2 = n.make_url("ABC", "DEF", "Team One", "Team Two", "epl", 100)
check("epl URL has rw_league=epl", "rw_league=epl" in url2, True)
check("epl URL has %20",           "Team%20One" in url2, True)
check("epl URL has %20 in two",    "Team%20Two" in url2, True)


# --- state load/save ---
import os, tempfile, json as _json
tmpdir = tempfile.mkdtemp()
os.environ["SXI_STATE_PATH"] = os.path.join(tmpdir, "state.json")
# Reload module
import importlib
importlib.reload(n)
n.STATE_PATH = n.Path(os.environ["SXI_STATE_PATH"])
state = n.load_state()
check("fresh state is empty",      len(state), 0)
state["test-match"] = {"home_sent": True, "away_sent": True}
n.save_state(state)
state2 = n.load_state()
check("state persists home_sent",  state2.get("test-match", {}).get("home_sent"), True)
del os.environ["SXI_STATE_PATH"]


# --- process_league logic (no Telegram) ---
# Use a stub for fetch_matches and send_telegram
original_fetch = n.fetch_matches
original_send = n.send_telegram

def stub_fetch(lk):
    if lk == "ucl":
        return [{
            "home_team": "Team A", "away_team": "Team B",
            "home_id": "A1", "away_id": "B1",
            "kickoff_ts": int(time.time()) + 600,  # 10 min from now
            "sxi_home_confirmed": True, "sxi_away_confirmed": False,
        }]
    return []

calls = []
def stub_send(text):
    calls.append(text)
    return True

n.fetch_matches = stub_fetch
n.send_telegram = stub_send

state = {}
sent = n.process_league("ucl", n.LEAGUES["ucl"], state)
check("first run: 1 notification sent", sent, 1)
check("first run: state has match",     "ucl-A1-B1" in state, True)
check("first run: home_sent=True",      state["ucl-A1-B1"]["home_sent"], True)
check("first run: away_sent=False",     state["ucl-A1-B1"]["away_sent"], False)
check("first run: side=home",           state["ucl-A1-B1"]["last_sent_side"], "home")

# Second call (idempotent — same state, no new side)
sent2 = n.process_league("ucl", n.LEAGUES["ucl"], state)
check("second run: 0 notifications",    sent2, 0)

# Now away gets confirmed — should send BOTH
def stub_fetch2(lk):
    if lk == "ucl":
        return [{
            "home_team": "Team A", "away_team": "Team B",
            "home_id": "A1", "away_id": "B1",
            "kickoff_ts": int(time.time()) + 600,
            "sxi_home_confirmed": True, "sxi_away_confirmed": True,
        }]
    return []

n.fetch_matches = stub_fetch2
calls.clear()
sent3 = n.process_league("ucl", n.LEAGUES["ucl"], state)
check("both-now: 1 notification sent",  sent3, 1)
check("both-now: state away_sent=True", state["ucl-A1-B1"]["away_sent"], True)
check("both-now: side=both",            state["ucl-A1-B1"]["last_sent_side"], "both")
check("both-now: 2 calls to send",      len(calls), 1)
# Format: "✅ Team A - Team B (url)✅" — leading ✅ on home, trailing ✅ on the closing paren
check("both-now: leading ✅",            "✅ Team A" in calls[0], True)
check("both-now: trailing ✅ after url", calls[0].rstrip().endswith(")✅"), True)

# Skip already-kicked-off matches
def stub_fetch3(lk):
    if lk == "ucl":
        return [{
            "home_team": "Old Match", "away_team": "X",
            "home_id": "X1", "away_id": "X2",
            "kickoff_ts": int(time.time()) - 3 * 3600,  # 3h ago
            "sxi_home_confirmed": True, "sxi_away_confirmed": True,
        }]
    return []
n.fetch_matches = stub_fetch3
calls.clear()
sent4 = n.process_league("ucl", n.LEAGUES["ucl"], state)
check("old match: 0 notifications",     sent4, 0)
check("old match: 0 send calls",        len(calls), 0)

# Restore
n.fetch_matches = original_fetch
n.send_telegram = original_send

# --- Summary ---
print(f"\n=== SUMMARY: {PASS} passed, {FAIL} failed ===")
if FAIL > 0:
    print("FAILURES:")
    for label, got, expected in FAILURES:
        print(f"  {label}: got {got!r}, expected {expected!r}")
    sys.exit(1)
print("all sxi_notifier guards pass")
