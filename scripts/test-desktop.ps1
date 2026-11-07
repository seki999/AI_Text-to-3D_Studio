$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
$package=Join-Path $studioRoot 'release/FORMA-AI-3D-Studio-0.4.0-x64.msi'
$testHome=Join-Path $studioRoot '.tools/v04-installed-smoke'
$installRoot=Join-Path $env:LOCALAPPDATA 'Programs/FORMA AI 3D Studio'
if (!(Test-Path -LiteralPath $package)) { throw 'Build the MSI first' }
$installed=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq 'FORMA AI 3D Studio' }
if ($installed) { throw 'A user installation already exists; this test will not replace or uninstall it. Use a clean Windows test account.' }
$install=Start-Process msiexec.exe -ArgumentList @('/i',"`"$package`"",'/qn','/norestart','/l*v',"`"$studioRoot/.tools/v04-install.log`"") -WindowStyle Hidden -PassThru -Wait
if ($install.ExitCode -notin @(0,3010)) { throw "MSI install failed: $($install.ExitCode)" }
$env:FORMA_TEST_HOME=$testHome
$app=Start-Process -FilePath (Join-Path $installRoot 'FormaStudio.exe') -ArgumentList @('--smoke-test','--smoke-worker') -WindowStyle Hidden -PassThru
if (!$app.WaitForExit(90000)) { Stop-Process -Id $app.Id -Force; throw 'Desktop smoke timeout; inspect test-home logs' }
$reportPath=Join-Path $testHome 'desktop-smoke.json'
$report=Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ($report.unauthenticated_status -ne 401) { throw 'Unauthorized backend access was not rejected' }
$browser=$report.browser | ConvertFrom-Json | ConvertFrom-Json
if (!$browser.canvas -or !$browser.body -or !$browser.native_model_loaded) { throw 'Production React Canvas did not load' }
Start-Sleep -Seconds 2
foreach ($managedId in $report.backend_pids) { if (Get-Process -Id $managedId -ErrorAction SilentlyContinue) { throw "Managed sidecar $managedId survived desktop exit" } }
$browserProcess=Get-Process -Id $report.browser_pid -ErrorAction SilentlyContinue
if ($browserProcess -and !$browserProcess.WaitForExit(15000)) { throw 'WebView2 browser survived desktop exit timeout' }
$beforeData=Test-Path -LiteralPath (Join-Path $testHome 'data/studio.sqlite3')
$uninstall=Start-Process msiexec.exe -ArgumentList @('/x',"`"$package`"",'/qn','/norestart','/l*v',"`"$studioRoot/.tools/v04-uninstall.log`"") -WindowStyle Hidden -PassThru -Wait
if ($uninstall.ExitCode -notin @(0,3010)) { throw "MSI uninstall failed: $($uninstall.ExitCode)" }
$result=[ordered]@{install_exit=$install.ExitCode;uninstall_exit=$uninstall.ExitCode;production_canvas=$browser.canvas;native_model_loaded=$browser.native_model_loaded;unauthorized_api=$report.unauthenticated_status;managed_pids_stopped=$true;webview_browser_stopped=$true;package_sha256=(Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant();package_bytes=(Get-Item -LiteralPath $package).Length;signed=$false;real_paid_api='not_run';data_preserved=($beforeData -and (Test-Path -LiteralPath (Join-Path $testHome 'data/studio.sqlite3')));application_removed=!(Test-Path -LiteralPath (Join-Path $installRoot 'FormaStudio.exe'));package=$package}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $studioRoot 'docs/v04-desktop-test.json') -Encoding utf8
$result | ConvertTo-Json
