#!/usr/bin/env python3
"""Fetch all LaLiga teams via fetch_team.py (with stadium from squad page)"""
import subprocess, sys, time

TEAMS = [
    ("SKbpVP5K", "Barcelona", "barcelona"),
    ("W8mj7MDD", "Real Madrid", "real-madrid"),
    ("lUatW5jE", "Villarreal", "villarreal"),
    ("jaarqpLQ", "Atl. Madrid", "atl-madrid"),
    ("vJbTeCGP", "Betis", "betis"),
    ("8pvUZFhf", "Celta Vigo", "celta-vigo"),
    ("dboeiWOt", "Getafe", "getafe"),
    ("8bcjFy6O", "Rayo Vallecano", "rayo-vallecano"),
    ("CQeaytrD", "Valencia", "valencia"),
    ("jNvak2f3", "Real Sociedad", "real-sociedad"),
    ("QFfPdh1J", "Espanyol", "espanyol"),
    ("IP5zl0cJ", "Ath Bilbao", "ath-bilbao"),
    ("h8oAv4Ts", "Sevilla", "sevilla"),
    ("hxt57t2q", "Alaves", "alaves"),
    ("G8FL0ShI", "Levante", "levante"),
    ("ETdxjU8a", "Osasuna", "osasuna"),
    ("4jl02tPF", "Elche", "elche"),
    ("nNNpcUSL", "Girona", "girona"),
    ("4jDQxrbf", "Mallorca", "mallorca"),
    ("SzYzw34K", "Oviedo", "real-oviedo"),
]

PYTHON = "/home/openclaw/FormAlert/.venv/bin/python3"
SCRIPT = "/home/openclaw/FormAlert/fetch_team.py"

ok, fail = [], []
t0 = time.time()

for i, (tid, name, slug) in enumerate(TEAMS, 1):
    print(f"\n{'='*60}")
    print(f"[{i}/{len(TEAMS)}] {name} ({tid})")
    print(f"{'='*60}")
    cmd = [PYTHON, SCRIPT, tid, "--full", "--team-name", name, "--slug", slug]
    t1 = time.time()
    r = subprocess.run(cmd, timeout=600)
    dt = time.time() - t1
    if r.returncode == 0:
        ok.append(name)
        print(f"  OK ({dt:.0f}s)")
    else:
        fail.append(name)
        print(f"  FAILED ({dt:.0f}s)")

print(f"\n{'='*60}")
print(f"Done in {time.time()-t0:.0f}s")
print(f"OK: {len(ok)} {ok}")
print(f"FAIL: {len(fail)} {fail}")
