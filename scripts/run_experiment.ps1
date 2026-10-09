<#
.SYNOPSIS
Runs the nested fraud experiment through the ordinary ExpOps runner.
.DESCRIPTION
Cloud deployment is explicit and may write to its configured output prefixes.
The local profile needs data/creditcard.csv and no cloud credentials.
#>
[CmdletBinding()]
param(
    [ValidateSet('local', 'cloud')]
    [string]$Deployment = 'local',
    [string]$ExpOpsExecutable = 'expops'
)

$ErrorActionPreference = 'Stop'
$command = (Get-Command $ExpOpsExecutable -CommandType Application -ErrorAction Stop).Source
$projectRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $projectRoot -Parent
$runRoot = Join-Path $projectRoot '.credit-card-fraud'
$previousEnvironment = @{}
foreach ($name in @('MLOPS_WORKSPACE_BASE_DIR', 'MLOPS_DATA_MATERIALIZATION_DIR', 'MLOPS_COMPUTE_CONFIG_PATH', 'MLOPS_WORKSPACE_DIR')) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

Push-Location -LiteralPath $workspaceRoot
try {
    if ($Deployment -eq 'local') {
        New-Item -ItemType Directory -Force -Path (Join-Path $runRoot 'storage') | Out-Null
    }
    $env:MLOPS_WORKSPACE_BASE_DIR = Join-Path $runRoot 'workspaces'
    $env:MLOPS_DATA_MATERIALIZATION_DIR = Join-Path $runRoot 'materialized'
    $env:MLOPS_WORKSPACE_DIR = $workspaceRoot
    $env:MLOPS_COMPUTE_CONFIG_PATH = Join-Path $projectRoot ('configs/compute.' + $Deployment + '.yaml')
    $arguments = @(
        'run', (Split-Path $projectRoot -Leaf), '--compute', $env:MLOPS_COMPUTE_CONFIG_PATH
    )
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Fraud experiment execution failed; check CLI stderr and run metadata.'
    }
} finally {
    Pop-Location
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
