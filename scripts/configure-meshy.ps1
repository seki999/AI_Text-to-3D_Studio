param([ValidateSet('set','status','delete')][string]$Action='set')
$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $studioRoot
try {
    & "$studioRoot/.venv/Scripts/python.exe" -X utf8 -m backend.app.ai3d.credentials $Action
    if ($LASTEXITCODE -ne 0) { throw 'Meshy local credential configuration failed' }
} finally { Pop-Location }
