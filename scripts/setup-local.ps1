$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$stackRoot = Split-Path $projectRoot -Parent
$toolsPython = Join-Path $stackRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $toolsPython)) {
    python -m venv (Join-Path $stackRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required for the I/O service environment.' }
}
& $toolsPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The tools/I/O environment needs Python 3.11 or newer.' }
& $toolsPython -m pip install uv
if ($LASTEXITCODE -ne 0) { throw 'Could not install uv.' }
& $toolsPython -m uv python install 3.10.22 --install-dir (Join-Path $stackRoot '.python') --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the isolated original-platform interpreter.' }
$python310 = Join-Path $stackRoot '.python/cpython-3.10.22-windows-x86_64-none/python.exe'
$originalPython = Join-Path $stackRoot '.venv-platform/Scripts/python.exe'
if (!(Test-Path -LiteralPath $originalPython)) {
    & $python310 -m venv (Join-Path $stackRoot '.venv-platform')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the original-platform environment.' }
}
$platformRoot = Join-Path $stackRoot 'expops-platform'
# Command-scoped Git configuration permits setuptools-scm to inspect this worktree.
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = $platformRoot
& $originalPython -m pip install -e $platformRoot -r (Join-Path $projectRoot 'requirements-runtime.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the baseline runtime dependencies.' }

# Prepare environments sequentially. The original bootstrap can race a pip
# self-upgrade and its chart subprocess uses the model environment's Python.
foreach ($name in @('fraud-model-env', 'fraud-reporting-env')) {
    $target = Join-Path $projectRoot ".credit-card-fraud/envs/$name"
    $targetPython = Join-Path $target 'Scripts/python.exe'
    if (!(Test-Path -LiteralPath $targetPython)) { & $originalPython -m venv $target }
    & $originalPython -m pip --python $targetPython install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare pip in $name." }
    & $originalPython -m pip --python $targetPython install -e $platformRoot -r (Join-Path $projectRoot 'requirements-runtime.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the original runtime in $name." }
}

# The original I/O module contains its own parsing helpers and never imports
# ExpOps. Keep its declared Python >=3.11 runtime separate from execution.
$ioRequirements = Join-Path $stackRoot '.venv/io-requirements.txt'
Copy-Item -LiteralPath (Join-Path $projectRoot 'requirements-io.lock.txt') -Destination $ioRequirements
& $toolsPython -m pip install -r $ioRequirements
if ($LASTEXITCODE -ne 0) { throw 'Could not install the original I/O service dependencies.' }
Push-Location (Join-Path $stackRoot 'expops-webapp')
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the original webapp dependencies.' }
} finally { Pop-Location }
