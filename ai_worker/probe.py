"""Runs inside the inference Python; imports Torch only here, never in the API venv."""
import importlib.util,json,os,platform,sys,hashlib,subprocess
from pathlib import Path
from .model_info import CKPT_BYTES,CONFIG_SHA256

def diagnose():
    repo=Path(os.getenv('HUNYUAN3D_REPO','')).resolve() if os.getenv('HUNYUAN3D_REPO') else None
    weights=Path(os.getenv('HUNYUAN3D_WEIGHTS','')).resolve() if os.getenv('HUNYUAN3D_WEIGHTS') else None
    dependencies={name:importlib.util.find_spec(name) is not None for name in ('torch','torchvision','PIL','trimesh','diffusers','transformers','accelerate','safetensors','omegaconf','einops','torchdiffeq','timm','cv2','skimage','scipy')}
    checkpoint=weights/'hunyuan3d-dit-v2-1' if weights else None
    weight_files=[p for p in checkpoint.glob('model.fp16.safetensors') if p.stat().st_size>1024] if checkpoint and checkpoint.is_dir() else []
    ckpt=checkpoint/'model.fp16.ckpt' if checkpoint else None
    if ckpt and ckpt.is_file() and ckpt.stat().st_size==CKPT_BYTES:weight_files.append(ckpt)
    config_ready=bool(checkpoint and (checkpoint/'config.yaml').is_file() and hashlib.sha256((checkpoint/'config.yaml').read_bytes()).hexdigest()==CONFIG_SHA256)
    result={'python':sys.version.split()[0],'platform':platform.system(),'dependencies':dependencies,'repo_ready':bool(repo and (repo/'hy3dshape/hy3dshape/pipelines.py').is_file()),'weights_ready':bool(weight_files and config_ready),'weights_directory':str(weights) if weights else None,'torch_cuda_available':None,'cuda_version':None,'gpus':[],'errors':[],'min_shape_vram_mb':10*1024,'min_texture_vram_mb':21*1024,'texture_ready':False,'source_revision':None,'weights_revision':None}
    if repo and repo.is_dir():
        try:
            query=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if query.returncode==0:result['source_revision']=query.stdout.strip()
        except (OSError,subprocess.SubprocessError):pass
    if weights and (weights/'MODEL-SOURCE.json').is_file():
        try:result['weights_revision']=json.loads((weights/'MODEL-SOURCE.json').read_text(encoding='utf-8')).get('revision')
        except (OSError,ValueError):pass
    if dependencies['torch']:
        try:
            import torch
            result.update(torch_version=torch.__version__,cuda_version=torch.version.cuda,torch_cuda_available=torch.cuda.is_available())
            if torch.cuda.is_available():
                for index in range(torch.cuda.device_count()):
                    free,total=torch.cuda.mem_get_info(index)
                    result['gpus'].append({'index':index,'name':torch.cuda.get_device_name(index),'vram_total_mb':total//1048576,'vram_available_mb':free//1048576})
        except Exception as exc:result['errors'].append('Torch CUDA 检测失败：'+type(exc).__name__)
    missing=[k for k,v in dependencies.items() if not v]
    if missing:result['errors'].append('推理环境缺少依赖：'+', '.join(missing))
    if not result['repo_ready']:result['errors'].append('未配置可信 HUNYUAN3D_REPO 源码目录')
    if not result['weights_ready']:result['errors'].append('未发现完整本地 model.fp16.ckpt / safetensors 与匹配的 config.yaml；不会自动下载')
    if result['torch_cuda_available'] is not True:result['errors'].append('未检测到可用 PyTorch CUDA；不启用未经验证的 CPU 回退')
    elif not result['gpus'] or result['gpus'][0]['vram_available_mb']<10*1024:result['errors'].append('当前可用显存不足 10 GiB Shape 门槛')
    result['available']=not result['errors']
    # Texture must be explicitly prepared; Shape availability does not imply Paint availability.
    paint=repo/'hy3dpaint' if repo else None
    if paint:sys.path.insert(0,str(paint/'DifferentiableRenderer'))
    result['texture_dependencies']={name:importlib.util.find_spec(name) is not None for name in ('custom_rasterizer_kernel','mesh_inpaint_processor','pymeshlab','xatlas','cupy','realesrgan','basicsr')}
    result['texture_ready']=bool(result['available'] and all(result['texture_dependencies'].values()) and os.getenv('HUNYUAN3D_ENABLE_TEXTURE')=='1' and paint and (paint/'ckpt/RealESRGAN_x4plus.pth').is_file() and weights and (weights/'hunyuan3d-paintpbr-v2-1').is_dir() and os.getenv('HUNYUAN3D_DINO_WEIGHTS') and Path(os.environ['HUNYUAN3D_DINO_WEIGHTS']).is_dir() and any(g['vram_available_mb']>=21*1024 for g in result['gpus']))
    return result

if __name__=='__main__':print(json.dumps(diagnose(),ensure_ascii=False))
