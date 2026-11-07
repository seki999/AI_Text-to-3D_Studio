$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
Push-Location frontend
try { npm.cmd run build; if ($LASTEXITCODE) { throw 'Frontend build failed' } } finally { Pop-Location }
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onedir --name FormaBackend --distpath release/engine --workpath build/pyinstaller --specpath build --paths $studioRoot --collect-submodules backend.app --collect-submodules ai_worker --collect-all fast_simplification --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on --add-data "$studioRoot/frontend/dist;web" --add-data "$studioRoot/backend/blender;backend/blender" backend/app/desktop_entry.py
if ($LASTEXITCODE) { throw 'Backend freezing failed' }
dotnet publish desktop/Forma.Desktop/Forma.Desktop.csproj -c Release -o release/FormaStudio
if ($LASTEXITCODE) { throw 'Desktop publish failed' }
$backendStage=Join-Path $studioRoot 'release/FormaStudio/backend'
if (Test-Path -LiteralPath $backendStage) { Move-Item -LiteralPath $backendStage -Destination (Join-Path $studioRoot ('build/backend-stage-'+[DateTime]::UtcNow.Ticks)) }
Copy-Item -LiteralPath release/engine/FormaBackend -Destination $backendStage -Recurse
Copy-Item LICENSE release/FormaStudio/LICENSE.txt -Force
& .venv/Scripts/python.exe -X utf8 desktop/licenses.py
& .venv/Scripts/python.exe -X utf8 desktop/build_installer.py
& .tools/wix/wix.exe build release/FormaStudio.wxs -arch x64 -o release/FORMA-AI-3D-Studio-0.4.0-x64.msi
if ($LASTEXITCODE) { throw 'MSI build failed' }
Get-FileHash release/FORMA-AI-3D-Studio-0.4.0-x64.msi -Algorithm SHA256
