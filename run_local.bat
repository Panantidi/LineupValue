@echo off
cd /d %~dp0
python -m pip install --user --break-system-packages -r requirements.txt
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
