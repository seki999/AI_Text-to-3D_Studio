$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath "$studioRoot/backend"
& "$studioRoot/.venv/Scripts/python.exe" -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
Set-Location -LiteralPath "$studioRoot/frontend"
npm.cmd test
if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
