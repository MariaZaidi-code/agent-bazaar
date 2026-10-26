$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv"
    }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip"
}

& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Agent Bazaar and the Auditor"
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
}

& $VenvPython -m pytest
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed"
}

& $VenvPython -m app.evaluation.run_all
if ($LASTEXITCODE -ne 0) {
    throw "Application evaluation failed"
}

& $VenvPython -m agent_bazaar_auditor evaluate
if ($LASTEXITCODE -ne 0) {
    throw "Auditor evaluation failed"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start the application with: .\.venv\Scripts\python.exe run.py"
Write-Host "Run the Auditor demo with: .\.venv\Scripts\agent-bazaar-auditor.exe demo"
