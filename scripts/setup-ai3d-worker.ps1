param(
    [switch]$InstallDependencies,
    [switch]$DownloadWeights,
    [switch]$AcceptModelLicense,
    [string]$EnvironmentPath=""
)
$ErrorActionPreference='Stop'
$studioRoot=Split-Path -Parent $PSScriptRoot
$studioEnv=if ($EnvironmentPath) { [System.IO.Path]::GetFullPath($EnvironmentPath) } else { Join-Path $studioRoot '.ai3d-venv' }
$studioSource=Join-Path $studioRoot '.tools/Hunyuan3D-2.1'
$studioWeights=Join-Path $studioRoot 'models/Hunyuan3D-2.1'
$studioRevision='82920d643c0dc2f7bfd7255f45f62d386edfe60c'
Set-Location -LiteralPath $studioRoot
if (!$InstallDependencies -and !$DownloadWeights) {
    Write-Host 'No downloads requested. Use -InstallDependencies to create a separate Python 3.11 environment.'
    Write-Host 'Read docs/GPU-SETUP.md and docs/MODEL-LICENSES.md before enabling inference.'
    if (Test-Path -LiteralPath "$studioEnv/Scripts/python.exe") { & "$studioEnv/Scripts/python.exe" -X utf8 -m ai_worker.probe }
    exit
}
if (!$AcceptModelLicense) { throw 'Read the upstream model license first, then explicitly pass -AcceptModelLicense. Project MIT does not license Hunyuan weights.' }
if ($InstallDependencies) {
    if (!(Test-Path -LiteralPath "$studioEnv/Scripts/python.exe")) {
        & py -3.11 -m venv $studioEnv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required. This script does not install a system Python or GPU driver.' }
    }
    $studioPythonVersion=& "$studioEnv/Scripts/python.exe" -c "import sys;print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"
    if ($studioPythonVersion -ne "3.11") { throw 'The secure Pillow requirement needs Python 3.11. Existing environments are never overwritten; pass -EnvironmentPath for a new isolated environment. Real Hunyuan compatibility still requires GPU validation.' }
    if (!(Test-Path -LiteralPath $studioSource)) {
        git clone --filter=blob:none https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git $studioSource
        if ($LASTEXITCODE -ne 0) { throw 'Source clone failed' }
        git -C $studioSource checkout $studioRevision
        if ($LASTEXITCODE -ne 0) { throw 'Source revision checkout failed' }
    }
    $studioActualRevision=git -C $studioSource rev-parse HEAD
    if ($studioActualRevision -ne $studioRevision) { throw 'Existing source differs from audited revision; review it explicitly, this script will not reset your source.' }
    & "$studioEnv/Scripts/python.exe" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
    if ($LASTEXITCODE -ne 0) { throw 'Torch installation failed; no driver changes were attempted' }
    & "$studioEnv/Scripts/python.exe" -m pip install -r ai_worker/requirements-shape.txt -r ai_worker/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Worker dependencies failed; API environment remains unchanged' }
}
if ($DownloadWeights) {
    if (!(Test-Path -LiteralPath "$studioEnv/Scripts/python.exe")) { throw 'Prepare the separate environment first' }
    $studioConfirmation=Read-Host 'This downloads large Hunyuan Shape weights (several GB) and accepts upstream license obligations. Type DOWNLOAD to confirm'
    if ($studioConfirmation -cne 'DOWNLOAD') { throw 'Weight download cancelled' }
    $env:HUNYUAN3D_WEIGHTS=$studioWeights
    & "$studioEnv/Scripts/python.exe" -c "import os,json,hashlib;from pathlib import Path;from huggingface_hub import snapshot_download;from ai_worker.model_info import WEIGHTS_REVISION,CKPT_SHA256;snapshot_download(repo_id='tencent/Hunyuan3D-2.1',revision=WEIGHTS_REVISION,local_dir=os.environ['HUNYUAN3D_WEIGHTS'],allow_patterns=['hunyuan3d-dit-v2-1/config.yaml','hunyuan3d-dit-v2-1/model.fp16.ckpt','LICENSE','Notice.txt']);p=Path(os.environ['HUNYUAN3D_WEIGHTS']);f=(p/'hunyuan3d-dit-v2-1/model.fp16.ckpt').open('rb');d=hashlib.sha256();[d.update(c) for c in iter(lambda:f.read(8388608),b'')];f.close();assert d.hexdigest()==CKPT_SHA256,'Checkpoint checksum mismatch';(p/'MODEL-SOURCE.json').write_text(json.dumps({'repository':'tencent/Hunyuan3D-2.1','revision':WEIGHTS_REVISION,'sha256':d.hexdigest()}),encoding='utf-8')"
    if ($LASTEXITCODE -ne 0) { throw 'Explicit weight download failed' }
}
$env:HUNYUAN3D_REPO=$studioSource
$env:HUNYUAN3D_WEIGHTS=$studioWeights
& "$studioEnv/Scripts/python.exe" -X utf8 -m ai_worker.probe
Write-Host 'No system environment variables or GPU drivers were modified. Export the printed paths in the worker terminal; see docs/GPU-SETUP.md.'
