"""Hardware measurements only. Missing GPU/CUDA measurements are null, never guesses."""
import importlib.util,json,os,platform,shutil,subprocess,sys
from pathlib import Path
import psutil

def hardware_report(data_dir:Path)->dict:
    memory=psutil.virtual_memory();disk=shutil.disk_usage(data_dir)
    result={'os':platform.system(),'python':sys.version.split()[0],'ram_total_bytes':memory.total,'ram_available_bytes':memory.available,'disk_free_bytes':disk.free,'gpus':[],'cuda_available':None,'torch_cuda_available':None,'torch_installed_in_api':importlib.util.find_spec('torch') is not None,'worker_python':None,'weights_ready':None,'notes':[]}
    smi=shutil.which('nvidia-smi')
    if smi:
        try:
            output=subprocess.run([smi,'--query-gpu=name,memory.total,memory.free,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,check=True)
            for line in output.stdout.splitlines():
                name,total,free,driver=[s.strip() for s in line.split(',')]
                result['gpus'].append({'name':name,'vendor':'NVIDIA','vram_total_mb':int(total),'vram_available_mb':int(free),'driver':driver})
        except (OSError,ValueError,subprocess.SubprocessError):result['notes'].append('nvidia-smi 存在但显存查询失败')
    if platform.system()=='Windows' and not result['gpus']:
        try:
            # AdapterRAM is a limited-width WMI field; intentionally never use it as VRAM.
            probe=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command','Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility | ConvertTo-Json -Compress'],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
            cards=json.loads(probe.stdout.decode('utf-8-sig',errors='replace'))
            for c in cards if isinstance(cards,list) else [cards]:result['gpus'].append({'name':c['Name'],'vendor':c['AdapterCompatibility'],'vram_total_mb':None,'vram_available_mb':None,'driver':None})
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):result['notes'].append('Windows GPU 信息查询失败，显示 Unknown')
    if not any(g['vendor']=='NVIDIA' for g in result['gpus']):result['notes'].append('未检测到可用 NVIDIA 显存信息；CUDA 和 PyTorch 状态由独立 Worker 确认')
    return result
