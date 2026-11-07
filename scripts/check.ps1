$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python scripts\check_bundle_budget.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$Node = Get-Command node -ErrorAction SilentlyContinue
if ($Node) {
    & node --check app\web\static\app.js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & node --check app\web\static\platform.js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & node --check app\web\static\utils.js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & node --check app\web\static\sw.js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Npm = Get-Command npm -ErrorAction SilentlyContinue
if ($Npm -and (Test-Path -LiteralPath (Join-Path $Root "node_modules"))) {
    & npm test
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $Python -m pytest -q
exit $LASTEXITCODE
