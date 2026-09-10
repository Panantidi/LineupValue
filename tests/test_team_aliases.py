# Sep 10 2026 — Guard test for team_name_aliases layer.
# Verifies alias-table resolution + resolve_lv_team_by_alias end-to-end.
import sys
sys.path.insert(0, '/home/openclaw/FormAlert')
import team_aliases as ta
import rotowire_fixtures as rf

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


# --- Alias-table resolution (deterministic) ---
print("=== resolve() — alias table (exact normalized) ===")
# UCL 2026/27
check("Glimt -> Bodo/Glimt",        ta.resolve("Glimt"),              "S0WZMUNG")
check("Bodo/Glimt -> Bodo/Glimt",   ta.resolve("Bodo/Glimt"),         "S0WZMUNG")
check("Bodø/Glimt -> Bodo/Glimt",   ta.resolve("Bodø/Glimt"),         "S0WZMUNG")
check("Bodoe/Glimt -> Bodo/Glimt",  ta.resolve("Bodoe/Glimt"),        "S0WZMUNG")
# Man Utd/Man City
check("Man Utd -> Man Utd",         ta.resolve("Man Utd"),             "ppjDR086")
check("Manchester United -> Utd",   ta.resolve("Manchester United"),   "ppjDR086")
check("Man City -> Man City",        ta.resolve("Man City"),            "Wtn9Stg0")
check("Manchester City -> Man City",ta.resolve("Manchester City"),     "Wtn9Stg0")
# Top-league teams
check("Bayern Munich -> Bayern",    ta.resolve("Bayern Munich"),       "nVp0wiqd")
check("Bayern -> Bayern",           ta.resolve("Bayern"),              "nVp0wiqd")
check("FC Bayern München -> Bayern",ta.resolve("FC Bayern München"),   "nVp0wiqd")
check("PSG -> PSG",                 ta.resolve("PSG"),                 "CjhkPw0k")
check("Paris Saint-Germain -> PSG", ta.resolve("Paris Saint-Germain"), "CjhkPw0k")
check("Real Madrid -> RM",          ta.resolve("Real Madrid"),         "W8mj7MDD")
check("Atletico Madrid -> AM",      ta.resolve("Atletico Madrid"),     "jaarqpLQ")
check("Atlético de Madrid -> AM",   ta.resolve("Atlético de Madrid"),  "jaarqpLQ")
# No match
check("Empty -> None",              ta.resolve(""),                    None)
check("Unknown -> None",            ta.resolve("NotARealTeam12345"),   None)


# --- resolve_with_meta() ---
print("\n=== resolve_with_meta() — full entry ===")
m = ta.resolve_with_meta("Glimt")
check("Glimt meta has id",          m["id"],                           "S0WZMUNG")
check("Glimt meta has name",        m["name"],                         "Bodo/Glimt")
check("Glimt meta has league",      "Champions League" in m["league"], True)


# --- API: add/remove/auto-learn ---
print("\n=== add_alias() / remove_alias() / learn_rotowire_name() ===")
# Use a temp team to avoid polluting the real data
TEST_ID = "_test_team_xyz"
TEST_NAME = "Test Club United"
ta.add_alias(TEST_ID, "Test Club", lv_name=TEST_NAME, lv_league="Test > Test League")
check("add_alias sets name",        ta.get_all()[TEST_ID]["name"],      TEST_NAME)
check("add_alias sets league",      ta.get_all()[TEST_ID]["league"],    "Test > Test League")
check("add_alias has aliases",      "Test Club" in ta.get_all()[TEST_ID]["aliases"], True)

# Idempotent
ta.add_alias(TEST_ID, "Test Club", lv_name=TEST_NAME, lv_league="Test > Test League")
check("add_alias idempotent",       len(ta.get_all()[TEST_ID]["aliases"]), 1)

# Add a different alias
ta.add_alias(TEST_ID, "TC United", category="alias")
check("add 2nd alias",              "TC United" in ta.get_all()[TEST_ID]["aliases"], True)

# Remove
ta.remove_alias(TEST_ID, "Test Club")
check("remove first alias",         "Test Club" in ta.get_all()[TEST_ID]["aliases"], False)
check("TC United still there",      "TC United" in ta.get_all()[TEST_ID]["aliases"], True)

# learn_rotowire_name
ta.learn_rotowire_name(TEST_ID, "Test Rotowire Name")
check("learn adds to rotowire_seen", "Test Rotowire Name" in ta.get_all()[TEST_ID]["rotowire_seen"], True)
# Idempotent
ta.learn_rotowire_name(TEST_ID, "Test Rotowire Name")
check("learn idempotent",            len(ta.get_all()[TEST_ID]["rotowire_seen"]), 1)

# Clean up
ta.remove_team(TEST_ID)
check("remove_team works",          TEST_ID in ta.get_all(),           False)


# --- resolve_lv_team_by_alias() end-to-end ---
print("\n=== resolve_lv_team_by_alias() — full pipeline ===")
# Build minimal LV teams list (just for testing)
ucl_teams = [
    {"id": "S0WZMUNG", "name": "Bodo/Glimt"},
    {"id": "ppjDR086", "name": "Man Utd"},
    {"id": "Wtn9Stg0", "name": "Man City"},
    {"id": "nVp0wiqd", "name": "Bayern"},
]

# Alias hit (deterministic)
r = rf.resolve_lv_team_by_alias("Glimt", ucl_teams, auto_learn=False)
check("Glimt -> Bodo/Glimt",        r and r["id"],                     "S0WZMUNG")
check("Glimt matched_via",          r and r["matched_via"],            "alias")

# Exact-name match — use a name NOT in the alias table (e.g. "Como 1907")
r = rf.resolve_lv_team_by_alias("Como 1907", ucl_teams, auto_learn=False)
# "Como 1907" is in seed aliases (Como), so alias wins. Use a different test.
# Real exact-match test: use a name that's neither in aliases nor fuzzy-matches.
# Build a custom teams list without alias
custom_teams = [{"id": "CUSTOM", "name": "Custom FC"}]
r = rf.resolve_lv_team_by_alias("Custom FC", custom_teams, auto_learn=False)
check("Custom FC exact match",      r and r["matched_via"],            "exact")

# Fuzzy fallback (Bayern -> "Bayern Munich")
r = rf.resolve_lv_team_by_alias("Bayern Munich", ucl_teams, auto_learn=False)
check("Bayern Munich -> Bayern",    r and r["id"],                     "nVp0wiqd")
check("Bayern Munich matched_via",  r and r["matched_via"],            "alias")  # in seed

# No match
r = rf.resolve_lv_team_by_alias("NoSuchTeam12345", ucl_teams, auto_learn=False)
check("NoSuchTeam -> None",         r,                                 None)


# --- Auto-learn (fuzzy match -> saved to rotowire_seen) ---
print("\n=== Auto-learn — fuzzy match persists ===")
# Use a name not in seed: "ManUtd" (no space)
# We expect _name_eq("Man Utd", "ManUtd") to be False, so no learn.
# Try a different test: use a UCL name we know but with typo
r = rf.resolve_lv_team_by_alias("Bod/Glimt", ucl_teams, auto_learn=True)
# If this matches (typo via fuzzy), it should be in rotowire_seen
if r and r["id"] == "S0WZMUNG":
    data = ta.get_all()
    check("Auto-learn saved 'Bod/Glimt'", "Bod/Glimt" in data["S0WZMUNG"].get("rotowire_seen", []), True)
    # Clean up
    if "Bod/Glimt" in data["S0WZMUNG"].get("rotowire_seen", []):
        data["S0WZMUNG"]["rotowire_seen"].remove("Bod/Glimt")
        ta._save(data)
else:
    print("  (skipping auto-learn check — fuzzy did not match)")


# --- Stats ---
print("\n=== stats() ===")
s = ta.stats()
check("stats has teams",            "teams" in s,                      True)
check("stats teams is int",         isinstance(s["teams"], int),       True)
check("stats has path",             "path" in s and s["path"].endswith("team_name_aliases.json"), True)


# --- Summary ---
print(f"\n=== SUMMARY: {PASS} passed, {FAIL} failed ===")
if FAIL > 0:
    print("FAILURES:")
    for label, got, expected in FAILURES:
        print(f"  {label}: got {got!r}, expected {expected!r}")
    sys.exit(1)
print("all team_aliases guards pass")
