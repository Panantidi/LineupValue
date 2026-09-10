"""Unit tests for pxi_notifier (no real Telegram)."""
import sys
sys.path.insert(0, '/home/openclaw/FormAlert')
import pxi_notifier as n

PASS = 0
FAIL = 0
FAILURES = []


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        # print(f"  OK  {label}")
    else:
        FAIL += 1
        FAILURES.append((label, got, want))
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


# --- build_message ---
m_full = {
    "home_team": "Como 1907",
    "away_team": "Lazio",
    "home_id": "ttyLthOA",
    "away_id": "abc12345",
    "kickoff_ts": 1789100000,  # 2026-09-11 22:13 CEST
    "lv_time": "11.09 22:13",
    "_league_key": "seri",
}
cfg = n.LEAGUES["seri"]

# home-only
text = n.build_message(cfg, m_full, "home")
check("home-only has 🎯 Predicted XI at start",  text.startswith("🎯 Predicted XI\nItaly - Serie A\nDate - 11.09 (22:13)\n✅"), True)
check("home-only contains <a href",  '<a href="' in text, True)
check("home-only link has match name", '>Como 1907 - Lazio</a>' in text, True)
check("home-only URL encoded in href", 'home_name=Como%201907' in text, True)
check("home-only has away_id",  'away_id=abc12345' in text, True)

# away-only
m_away = dict(m_full)
m_away["pxi_home_total"] = 0
m_away["pxi_away_total"] = 8
text = n.build_message(cfg, m_away, "away")
check("away-only ends with </a> ✅",     text.rstrip().endswith("</a> ✅"), True)

# both
m_both = dict(m_full)
m_both["pxi_home_total"] = 11
m_both["pxi_away_total"] = 11
text = n.build_message(cfg, m_both, "both")
check("both starts with ✅ <a",        text.startswith("🎯 Predicted XI\nItaly - Serie A\nDate - 11.09 (22:13)\n✅ <a "), True)
check("both ends with </a> ✅",         text.rstrip().endswith("</a> ✅"), True)

# No kickoff time provided
m_no_ts = {
    "home_team": "A", "away_team": "B",
    "home_id": "aa", "away_id": "bb",
    "kickoff_ts": 0, "lv_time": "",
    "_league_key": "seri",
}
text = n.build_message(cfg, m_no_ts, "home")
check("no ts: shows ?? in parens",  "??.? (??)" in text, True)

# --- URL contains all required params ---
url = n.make_url("ttyLthOA", "abc12345", "Como 1907", "Lazio", "seri", 1789100000)
check("url contains mid",            "mid=px-ttyLthOA-abc12345" in url, True)
check("url contains rotowire_fran=1", "rotowire_fran=1" in url, True)
check("url contains rw_league=seri",  "rw_league=seri" in url, True)
check("url has %20 (not +)",         "Como%201907" in url, True)
check("url has Lazio%20",            "Lazio" in url, True)

# --- process_league: tests with stub fetch/send ---
calls = []
def stub_send(msg):
    calls.append(msg)
    return True

def stub_fetch1(lk):
    return [{
        "home_team": "Team A", "away_team": "Team B",
        "home_id": "A1", "away_id": "B1",
        "kickoff_ts": int(__import__("time").time()) + 3600,  # 1h from now
        "lv_time": "11.09 22:00",
        "pxi_home_matched": 11, "pxi_home_total": 11,  # home P-XI published
        "pxi_away_matched": 0,  "pxi_away_total": 0,
    }]

import pxi_notifier
orig_send = pxi_notifier.send_telegram
orig_fetch = pxi_notifier.fetch_matches
pxi_notifier.send_telegram = stub_send
pxi_notifier.fetch_matches = stub_fetch1

# Initial: empty state
state = {}
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state, int(__import__("time").time()))
check("home-only P-XI: 1 call to send",       len(calls), 1)
check("home-only P-XI: text has Italy-Serie A", "Italy - Serie A" in calls[0], True)
check("home-only P-XI: text has 🎯",         "🎯 Predicted XI" in calls[0], True)
check("home-only P-XI: state home_sent=True",  state["seri-A1-B1"]["home_sent"], True)
check("home-only P-XI: state away_sent=False", state["seri-A1-B1"]["away_sent"], False)
check("home-only P-XI: state last_sent_side=home", state["seri-A1-B1"]["last_sent_side"], "home")

# Now away also published
calls.clear()
def stub_fetch2(lk):
    return [{
        "home_team": "Team A", "away_team": "Team B",
        "home_id": "A1", "away_id": "B1",
        "kickoff_ts": int(__import__("time").time()) + 3600,
        "lv_time": "11.09 22:00",
        "pxi_home_matched": 11, "pxi_home_total": 11,
        "pxi_away_matched": 8,  "pxi_away_total": 8,
    }]

pxi_notifier.fetch_matches = stub_fetch2
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state, int(__import__("time").time()))
check("away also: 1 call to send (the new one)", len(calls), 1)
check("away also: state home_sent=True",         state["seri-A1-B1"]["home_sent"], True)
check("away also: state away_sent=True",         state["seri-A1-B1"]["away_sent"], True)
check("away also: state last_sent_side=both",    state["seri-A1-B1"]["last_sent_side"], "both")
check("away also: text has both ✅",             "✅ " in calls[0] and calls[0].rstrip().endswith("</a> ✅"), True)

# Already both confirmed — no new send
calls.clear()
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state, int(__import__("time").time()))
check("already both: 0 calls", len(calls), 0)

# --- Skip matches where neither side has P-XI published ---
def stub_fetch_none(lk):
    return [{
        "home_team": "X", "away_team": "Y",
        "home_id": "X1", "away_id": "Y1",
        "kickoff_ts": int(__import__("time").time()) + 3600,
        "pxi_home_matched": 0, "pxi_home_total": 0,
        "pxi_away_matched": 0, "pxi_away_total": 0,
    }]

calls.clear()
state2 = {}
pxi_notifier.fetch_matches = stub_fetch_none
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state2, int(__import__("time").time()))
check("no P-XI: 0 calls",   len(calls), 0)
check("no P-XI: state empty", len(state2), 0)

# --- Skip matches > 2h past kickoff ---
def stub_fetch_old(lk):
    return [{
        "home_team": "X", "away_team": "Y",
        "home_id": "X1", "away_id": "Y1",
        "kickoff_ts": int(__import__("time").time()) - 3 * 3600,  # 3h ago
        "pxi_home_matched": 11, "pxi_home_total": 11,
        "pxi_away_matched": 0,  "pxi_away_total": 0,
    }]

calls.clear()
state3 = {}
pxi_notifier.fetch_matches = stub_fetch_old
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state3, int(__import__("time").time()))
check("3h past kickoff: 0 calls", len(calls), 0)

# --- Skip matches with no IDs ---
def stub_fetch_no_ids(lk):
    return [{
        "home_team": "X", "away_team": "Y",
        "home_id": "", "away_id": "",
        "kickoff_ts": int(__import__("time").time()) + 3600,
        "pxi_home_matched": 11, "pxi_home_total": 11,
        "pxi_away_matched": 0,  "pxi_away_total": 0,
    }]

calls.clear()
state4 = {}
pxi_notifier.fetch_matches = stub_fetch_no_ids
sent = pxi_notifier.process_league("seri", n.LEAGUES["seri"], state4, int(__import__("time").time()))
check("no IDs: 0 calls", len(calls), 0)

# --- match_key ---
check("match_key format", n.match_key("ucl", "ppj", "fng"), "ucl-ppj-fng")

# --- restore ---
pxi_notifier.send_telegram = orig_send
pxi_notifier.fetch_matches = orig_fetch

print(f"\n=== SUMMARY: {PASS} passed, {FAIL} failed ===")
if FAIL > 0:
    print("\nFAILURES:")
    for label, got, want in FAILURES:
        print(f"  {label}: got {got!r}, want {want!r}")
    sys.exit(1)
print("all pxi_notifier guards pass")
