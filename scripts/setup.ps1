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
    throw "Failed to install agent-bazaar-auditor"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
Write-Host "Then run: agent-bazaar-auditor demo"
