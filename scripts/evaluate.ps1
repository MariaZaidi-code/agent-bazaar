$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment missing. Run scripts\setup.ps1 first."
}

& ".\.venv\Scripts\python.exe" -m app.evaluation.run_all
