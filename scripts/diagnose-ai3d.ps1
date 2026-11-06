param([string]$WorkerPython='')
$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
& "$studioRoot/.venv/Scripts/python.exe" -X utf8 -c "from pathlib import Path;import json;from backend.app.ai3d.diagnostics import hardware_report;print(json.dumps(hardware_report(Path('.')),ensure_ascii=False,indent=2))"
if (!$WorkerPython) { $WorkerPython=Join-Path $studioRoot '.ai3d-venv/Scripts/python.exe' }
if (Test-Path -LiteralPath $WorkerPython) { & $WorkerPython -X utf8 -m ai_worker.probe } else { Write-Host 'Independent worker Python: Unknown / not installed. No CUDA packages or weights were installed by diagnostics.' }
