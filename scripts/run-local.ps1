. (Join-Path $PSScriptRoot 'use-original.ps1')
# setup-local.ps1 has already prepared the interpreters. Keep the original CLI
# in the foreground instead of its Windows os.execv bootstrap handoff.
$env:MLOPS_ENV_READY = '1'
Push-Location $stackRoot
try {
    & $originalPython -m expops run credit-card-fraud --local
    if ($LASTEXITCODE -ne 0) { throw 'The original pipeline failed; inspect the project runtime logs.' }
} finally { Pop-Location }
