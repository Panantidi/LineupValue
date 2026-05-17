Set-Location $PSScriptRoot
python -m pip install --user --break-system-packages -r requirements.txt
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
