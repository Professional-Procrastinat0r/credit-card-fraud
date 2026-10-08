<#
.SYNOPSIS
Runs the fraud VFS control through the ordinary ExpOps runner.
.DESCRIPTION
Cloud deployment is explicit and may write to its configured output prefixes.
This script never changes the legacy experiment or stores credential values.
#>
[CmdletBinding()]
param(
    [ValidateSet('local', 'cloud')]
    [string]$Deployment = 'local',
    [string]$ExpOpsExecutable = 'expops'
)

$ErrorActionPreference = 'Stop'
$command = (Get-Command $ExpOpsExecutable -CommandType Application -ErrorAction Stop).Source
$vfsRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'vfs'
$runRoot = Join-Path $vfsRoot '.run'
$previousEnvironment = @{}
foreach ($name in @('MLOPS_WORKSPACE_BASE_DIR', 'MLOPS_DATA_MATERIALIZATION_DIR', 'MLOPS_COMPUTE_CONFIG_PATH', 'MLOPS_WORKSPACE_DIR')) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

Push-Location -LiteralPath $vfsRoot
try {
    if ($Deployment -eq 'local') {
        New-Item -ItemType Directory -Force -Path (Join-Path $vfsRoot '.storage') | Out-Null
    }
    $env:MLOPS_WORKSPACE_BASE_DIR = Join-Path $runRoot 'workspaces'
    $env:MLOPS_DATA_MATERIALIZATION_DIR = Join-Path $runRoot 'materialized'
    $arguments = @(
        'run', '--compute', ('compute.' + $Deployment + '.yaml'), '--project', 'project'
    )
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Fraud VFS execution failed; check CLI stderr and run metadata.'
    }
} finally {
    Pop-Location
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
