param([switch]$SimulateFailureAfterInstall)
$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
$package=Join-Path $studioRoot 'release/FORMA-AI-3D-Studio-0.4.0-x64.msi'
$runId=[Guid]::NewGuid().ToString('N')
$testHome=Join-Path $studioRoot ('.tools/v04-installed-smoke/'+$runId)
$installRoot=Join-Path $env:LOCALAPPDATA 'Programs/FORMA AI 3D Studio'
if (!(Test-Path -LiteralPath $package)) { throw 'Build the MSI first' }
$installed=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq 'FORMA AI 3D Studio' }
if ($installed -or (Test-Path -LiteralPath (Join-Path $installRoot 'FormaStudio.exe'))) { throw 'A user installation already exists; this test will not replace or uninstall it. Use a clean Windows test account.' }
$previousTestHome=$env:FORMA_TEST_HOME
$installedByTest=$false
$verificationError=$null
$beforeData=$false
$result=[ordered]@{run_id=$runId;status='running';install_exit=$null;uninstall_exit=$null;production_canvas=$null;native_model_loaded=$null;unauthorized_api=$null;managed_pids_stopped=$null;webview_browser_stopped=$null;fresh_report=$null;package_sha256=(Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant();package_bytes=(Get-Item -LiteralPath $package).Length;signed=((Get-AuthenticodeSignature -FilePath $package).Status -eq 'Valid');real_paid_api='not_run';data_preserved=$null;application_removed=$null;package=$package;test_home=$testHome;failure_injected=[bool]$SimulateFailureAfterInstall}
try {
    $install=Start-Process msiexec.exe -ArgumentList @('/i',"`"$package`"",'/qn','/norestart','/l*v',"`"$studioRoot/.tools/v04-install.log`"") -WindowStyle Hidden -PassThru -Wait
    $result.install_exit=$install.ExitCode
    if ($install.ExitCode -notin @(0,3010)) { throw "MSI install failed: $($install.ExitCode)" }
    $installedByTest=$true
    if ($SimulateFailureAfterInstall) { throw 'Intentional installer verification failure (cleanup test)' }
    $env:FORMA_TEST_HOME=$testHome
    $started=[DateTime]::UtcNow
    $app=Start-Process -FilePath (Join-Path $installRoot 'FormaStudio.exe') -ArgumentList @('--smoke-test','--smoke-worker') -WindowStyle Hidden -PassThru
    if (!$app.WaitForExit(90000)) { Stop-Process -Id $app.Id -Force; throw 'Desktop smoke timeout; inspect test-home logs' }
    if ($app.ExitCode -ne 0) { throw "Desktop exited with code $($app.ExitCode)" }
    $reportPath=Join-Path $testHome 'desktop-smoke.json'
    if (!(Test-Path -LiteralPath $reportPath) -or (Get-Item -LiteralPath $reportPath).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'No fresh smoke report from this invocation; previous reports are not accepted' }
    $result.fresh_report=$true
    $report=Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $result.unauthorized_api=$report.unauthenticated_status
    if ($report.unauthenticated_status -ne 401) { throw 'Unauthorized backend access was not rejected' }
    $browser=$report.browser | ConvertFrom-Json | ConvertFrom-Json
    $result.production_canvas=$browser.canvas
    $result.native_model_loaded=$browser.native_model_loaded
    if (!$browser.canvas -or !$browser.body -or !$browser.native_model_loaded) { throw 'Production React Canvas did not load' }
    Start-Sleep -Seconds 2
    foreach ($managedId in $report.backend_pids) { if (Get-Process -Id $managedId -ErrorAction SilentlyContinue) { throw "Managed sidecar $managedId survived desktop exit" } }
    $result.managed_pids_stopped=$true
    $browserProcess=Get-Process -Id $report.browser_pid -ErrorAction SilentlyContinue
    if ($browserProcess -and !$browserProcess.WaitForExit(15000)) { throw 'WebView2 browser survived desktop exit timeout' }
    $result.webview_browser_stopped=$true
    $beforeData=Test-Path -LiteralPath (Join-Path $testHome 'data/studio.sqlite3')
    if (!$beforeData) { throw 'Desktop did not persist its database' }
} catch {
    $verificationError=$_.Exception.Message
    $result.error=$verificationError
} finally {
    $env:FORMA_TEST_HOME=$previousTestHome
    if ($installedByTest) {
        try {
            $uninstall=Start-Process msiexec.exe -ArgumentList @('/x',"`"$package`"",'/qn','/norestart','/l*v',"`"$studioRoot/.tools/v04-uninstall.log`"") -WindowStyle Hidden -PassThru -Wait
            $result.uninstall_exit=$uninstall.ExitCode
            if ($uninstall.ExitCode -notin @(0,3010)) { throw "MSI uninstall failed: $($uninstall.ExitCode)" }
            $result.application_removed=!(Test-Path -LiteralPath (Join-Path $installRoot 'FormaStudio.exe'))
            if (!$result.application_removed) { throw 'Installed executable survived uninstall' }
            if ($beforeData) {
                $result.data_preserved=Test-Path -LiteralPath (Join-Path $testHome 'data/studio.sqlite3')
                if (!$result.data_preserved) { throw 'Uninstall removed user data' }
            }
        } catch {
            $result.cleanup_error=$_.Exception.Message
            if (!$verificationError) { $verificationError=$_.Exception.Message }
        }
    }
    $result.status=if ($verificationError) {'failed'} else {'passed'}
    $reportName=if ($SimulateFailureAfterInstall) {'v04-desktop-failure-test.json'} else {'v04-desktop-test.json'}
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $studioRoot ('docs/'+$reportName)) -Encoding utf8
    $result | ConvertTo-Json
}
if ($verificationError) { throw $verificationError }
