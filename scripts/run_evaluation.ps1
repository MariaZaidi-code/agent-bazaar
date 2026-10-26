param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $EvaluateArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    & $VenvPython -m agent_bazaar_auditor evaluate @EvaluateArgs
} else {
    & python -m agent_bazaar_auditor evaluate @EvaluateArgs
}

exit $LASTEXITCODE
