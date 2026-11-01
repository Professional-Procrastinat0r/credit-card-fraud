param([int]$Port = 8080)
$ErrorActionPreference = 'Stop'
$stackRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ioPython = Join-Path $stackRoot '.venv/Scripts/python.exe'
Push-Location (Join-Path $stackRoot 'expops-services/io-service')
try { & $ioPython -m uvicorn server:app --host 127.0.0.1 --port $Port }
finally { Pop-Location }
