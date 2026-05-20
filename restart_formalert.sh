#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/user/lineupvalue_export
./.venv/bin/python -m py_compile lineup_team_view.py
pkill -9 -f '/home/openclaw/FormAlert/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099' || true
sleep 1
sshpass -p 'Chelsea777!' ssh -o Ciphers=aes128-ctr -o Compression=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ConnectTimeout=15 -o StrictHostKeyChecking=no -p 2091 openclaw@212.193.4.121 "cd /home/openclaw/FormAlert && nohup ./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099 >/tmp/formalert-uvicorn.log 2>&1 </dev/null &"
sleep 4
sshpass -p 'Chelsea777!' ssh -o Ciphers=aes128-ctr -o Compression=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ConnectTimeout=15 -o StrictHostKeyChecking=no -p 2091 openclaw@212.193.4.121 "pgrep -af '/home/openclaw/FormAlert/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8099' || true; echo ---; ss -ltnp | grep 8099 || true; echo ---; curl -s http://127.0.0.1:8099/lineup_ai/FL1010 | grep -n 'Total Value\|Starting XI Impact Score\|MV Starting XI\|Av.Age Starting XI\|Total Apps\|Total Assists\|Yellow Cards' | sed -n '1,120p'; echo ---LOG---; tail -n 20 /tmp/formalert-uvicorn.log || true"