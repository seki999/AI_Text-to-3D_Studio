$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) { python -m venv .venv }
& ./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed' }
Push-Location frontend
try {
    if (!(Test-Path -LiteralPath 'node_modules')) { npm.cmd ci }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependencies failed' }
} finally { Pop-Location }
if (!$env:BLENDER_PATH) {
    $studioBlender = Get-ChildItem -LiteralPath "$studioRoot/.tools" -Filter blender.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($studioBlender) { $env:BLENDER_PATH = $studioBlender.FullName }
}
$studioBackend = Start-Process -FilePath "$studioRoot/.venv/Scripts/python.exe" -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory "$studioRoot/backend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$studioRoot/backend/server.log" -RedirectStandardError "$studioRoot/backend/server-error.log"
Write-Host 'Studio: http://127.0.0.1:5173  | API: http://127.0.0.1:8000/docs'
try { Set-Location -LiteralPath "$studioRoot/frontend"; npm.cmd run dev } finally { Stop-Process -Id $studioBackend.Id -ErrorAction SilentlyContinue }
