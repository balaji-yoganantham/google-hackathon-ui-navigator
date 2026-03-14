# Run the UI Navigator Python backend (Windows-friendly: uses ProactorEventLoop)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$venvPython = Join-Path $scriptDir "venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "venv not found. Run: python -m venv venv && venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}

Set-Location $backendDir
& $venvPython run_server.py
