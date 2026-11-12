# Serve the Oathbox API + web app on http://127.0.0.1:8000  (Windows PowerShell)
Set-Location (Split-Path $PSScriptRoot -Parent)
& backend\.venv\Scripts\python.exe -m uvicorn oathbox.app:app --app-dir backend --host 127.0.0.1 --port 8000
