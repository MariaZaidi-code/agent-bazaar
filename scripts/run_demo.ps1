$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    & $VenvPython -m agent_bazaar_auditor demo
} else {
    & python -m agent_bazaar_auditor demo
}

exit $LASTEXITCODE
