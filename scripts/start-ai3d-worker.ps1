param([string]$Python='', [switch]$MockTestMode)
$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
if (!$Python) { $Python=Join-Path $studioRoot '.ai3d-venv/Scripts/python.exe' }
if (!(Test-Path -LiteralPath $Python)) { throw 'Independent Python environment missing; read docs/GPU-SETUP.md. For explicit Mock tests you may pass .venv/Scripts/python.exe.' }
if (!$env:AI3D_WORKER_TOKEN -or $env:AI3D_WORKER_TOKEN.Length -lt 16) { throw 'Set the same random AI3D_WORKER_TOKEN in worker and API terminals (at least 16 characters).' }
if ($MockTestMode) { $env:AI3D_ENABLE_MOCK='1';Write-Host 'MOCK TEST MODE ONLY: output is fixture geometry, never neural AI inference.' }
if (!$env:HUNYUAN3D_REPO) { $env:HUNYUAN3D_REPO=Join-Path $studioRoot '.tools/Hunyuan3D-2.1' }
if (!$env:HUNYUAN3D_WEIGHTS) { $env:HUNYUAN3D_WEIGHTS=Join-Path $studioRoot 'models/Hunyuan3D-2.1' }
$env:PYTHONUTF8='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
& $Python -m uvicorn ai_worker.service:app --host 127.0.0.1 --port 8010
