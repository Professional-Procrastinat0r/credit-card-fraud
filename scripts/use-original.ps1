$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$stackRoot = Split-Path $projectRoot -Parent
$platformRoot = Join-Path $stackRoot 'expops-platform'
$originalPython = Join-Path $stackRoot '.venv-platform/Scripts/python.exe'
if (!(Test-Path -LiteralPath $originalPython)) { throw 'Run scripts/setup-local.ps1 first.' }
$expectedCommit = 'a3e6107d8182b928a116098931af66e3df110208'
$actualCommit = git -c "safe.directory=$platformRoot" -C $platformRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) { throw 'The original platform checkout must be pinned to a3e6107.' }

$env:PYTHONPATH = Join-Path $platformRoot 'src'
$env:MLOPS_WORKSPACE_DIR = $stackRoot
$env:MLOPS_PROJECT_ID = 'credit-card-fraud'
$env:MLOPS_KV_BACKEND = 'local'
$env:MLOPS_KV_PATH = Join-Path $projectRoot 'kv_store.db'
$env:MLOPS_FORCE_LOCAL = '1'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MPLCONFIGDIR = Join-Path $projectRoot '.credit-card-fraud/matplotlib'
Remove-Item Env:MLOPS_ENV_READY -ErrorAction SilentlyContinue

& $originalPython -c "import sys, expops, lz4.frame; print(sys.executable); print(expops.__file__)"
if ($LASTEXITCODE -ne 0) { throw 'The original platform runtime failed its import check.' }
