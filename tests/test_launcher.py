"""Windows launcher must restore its caller even when the CLI fails."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher acceptance")
def test_launcher_restores_cwd_and_environment_after_failed_child(tmp_path):
    shell = shutil.which("powershell")
    if shell is None:
        pytest.skip("Windows PowerShell is unavailable")
    launcher = Path(__file__).resolve().parents[1] / "scripts/run_experiment.ps1"

    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    # Python deliberately rejects the CLI's `run` argument. No cloud client,
    # wheel installation or source import is invoked by this failure-path test.
    script = f"""
$ErrorActionPreference = 'Stop'
$env:MLOPS_WORKSPACE_BASE_DIR = 'caller-owned-workspace'
[Environment]::SetEnvironmentVariable('MLOPS_DATA_MATERIALIZATION_DIR', $null, 'Process')
$env:MLOPS_WORKSPACE_DIR = 'caller-owned-projects'
$env:MLOPS_COMPUTE_CONFIG_PATH = 'caller-owned-config'
$before = (Get-Location).Path
$failed = $false
try {{
    & {quote(launcher)} -Deployment cloud -ExpOpsExecutable {quote(sys.executable)}
}} catch {{
    if ($_.Exception.Message -ne 'Fraud experiment execution failed; check CLI stderr and run metadata.') {{ throw }}
    $failed = $true
}}
if (-not $failed) {{ throw 'Expected the test child to fail' }}
if ((Get-Location).Path -ne $before) {{ throw 'Caller CWD was not restored' }}
if ($env:MLOPS_WORKSPACE_BASE_DIR -ne 'caller-owned-workspace') {{ throw 'Caller environment was changed' }}
if ($null -ne [Environment]::GetEnvironmentVariable('MLOPS_DATA_MATERIALIZATION_DIR', 'Process')) {{
    throw 'Originally absent environment variable was not restored'
}}
if ($env:MLOPS_WORKSPACE_DIR -ne 'caller-owned-projects') {{ throw 'Caller workspace changed' }}
if ($env:MLOPS_COMPUTE_CONFIG_PATH -ne 'caller-owned-config') {{ throw 'Caller config changed' }}
Write-Output 'launcher-restored'
"""
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "launcher-restored" in result.stdout
