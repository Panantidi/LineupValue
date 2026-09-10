# Sep 7 2026 — Guard test: ensure _name_eq pairs (rotowire name -> LV name)
# all return the expected value. Catches regressions like NYC FC <-> NY Red Bulls.
import sys
sys.path.insert(0, '/home/openclaw/FormAlert')
from rotowire_fixtures import _name_eq as f

# Each entry: (rotowire_name, lv_name, expected_match, comment)
CASES = [
    # NYC: rotowire "New York City FC" must match LV "New York City", NOT LV "New York Red Bulls"
    ('New York City FC', 'New York City', True, 'NYCFC -> NYC'),
    ('New York City FC', 'New York Red Bulls', False, 'NYCFC must NOT match Red Bulls'),
    ('New York Red Bulls', 'New York Red Bulls', True, 'NYRB -> NYRB'),
    ('New York Red Bulls', 'New York City', False, 'NYRB must NOT match NYC'),

    # LA: "Los Angeles Football Club" -> LV "Los Angeles FC", NOT "Los Angeles Galaxy"
    ('Los Angeles Football Club', 'Los Angeles FC', True, 'LAFC rotowire -> LAFC LV'),
    ('Los Angeles Football Club', 'Los Angeles Galaxy', False, 'LAFC must NOT match Galaxy'),
    ('Los Angeles Galaxy', 'Los Angeles Galaxy', True, 'LAG -> LAG'),
    ('Los Angeles Galaxy', 'Los Angeles FC', False, 'LAG must NOT match LAFC'),

    # Generic: "Atlanta United" / "DC United" share only "united"
    ('Atlanta United', 'Atlanta United', True, 'self'),
    ('Atlanta United', 'DC United', False, 'different cities, only "united" shared'),
    ('D.C. United', 'DC United', True, 'punctuation variant'),

    # Abbrev: "Inter Miami CF" -> LV "Inter Miami"
    ('Inter Miami CF', 'Inter Miami', True, 'Inter Miami CF -> Inter Miami'),
    ('Real Salt Lake', 'Real Salt Lake', True, 'self'),

    # Cross-league: "Bayern Munich" / "Bayern Munchen"
    ('Bayern Munich', 'Bayern Munchen', True, 'umlaut tolerance'),
    ('Real Madrid', 'Real Sociedad', False, 'different clubs'),

    # Generic token reject (city/united/fc as only shared)
    ('Charlotte FC', 'Charlotte', True, 'abbrev city'),
    ('Charlotte FC', 'DC United', False, 'no real match'),
    ('New York City FC', 'Charlotte FC', False, 'cross-team false positive guard'),

    # Sep 10 2026 — Man Utd guards (UCL use case).
    # _name_eq may match both via prefix-cross, but _match_score picks the right one.
    ('Manchester United', 'Man Utd', True, 'UCL: Manchester United -> Man Utd'),
    ('Manchester United', 'Man City', True, '_name_eq also matches Man City (select via _match_score)'),
    ('Man Utd', 'Man City', False, 'different clubs'),
    ('Man City', 'Manchester City', True, 'Manchester City -> Man City'),
]

fails = 0
for rw, lv, exp, note in CASES:
    got = f(rw, lv)
    ok = got == exp
    if not ok:
        fails += 1
    print(f'{"OK" if ok else "FAIL"}  {rw!r:35s} vs {lv!r:25s} -> {got}  (expected {exp})  [{note}]')

if fails:
    print(f'\n{fails} test(s) FAILED')
    sys.exit(1)
print('\nall _name_eq guards pass')
