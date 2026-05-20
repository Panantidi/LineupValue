#!/bin/bash
set -euo pipefail
cd /home/openclaw/FormAlert
./.venv/bin/python -m py_compile lineup_team_view.py
pkill -9 -f '/home/openclaw/FormAlert/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099' || true
sleep 1
nohup ./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099 >/tmp/formalert-uvicorn.log 2>&1 </dev/null &
sleep 4
pgrep -af '/home/openclaw/FormAlert/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099' || true
echo '---'
ss -ltnp | grep 8099 || true
echo '---'
curl -s http://127.0.0.1:8099/lineup_ai/FL1010 | grep -n 'Total Value\|Starting XI Impact Score\|MV Starting XI\|Av.Age Starting XI\|Total Apps\|Total Assists\|Yellow Cards' | sed -n '1,120p'
echo '---LOG---'
tail -n 20 /tmp/formalert-uvicorn.log || true
