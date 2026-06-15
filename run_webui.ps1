# Launch the SynthRange admin panel.
# Usage:  .\run_webui.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "venv not found - run: python -m venv venv; .\venv\Scripts\python.exe -m pip install -r requirements.txt"; exit 1 }
Write-Host "SynthRange admin panel -> http://127.0.0.1:5000" -ForegroundColor Cyan
Start-Process "http://127.0.0.1:5000"
& $py (Join-Path $here "webui\app.py")
