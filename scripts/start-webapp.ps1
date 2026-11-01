param([int]$Port = 3000)
. (Join-Path $PSScriptRoot 'use-original.ps1')
$env:EXPOPS_SQLITE_DIR = $stackRoot
Push-Location (Join-Path $stackRoot 'expops-webapp')
try { npm.cmd run dev -- --webpack --hostname 127.0.0.1 --port $Port }
finally { Pop-Location }
