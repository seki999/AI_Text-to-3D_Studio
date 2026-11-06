"""Trusted child process. Inputs select whitelisted pipelines; no generated code execution."""
import gc,json,os,sys,time,hashlib
from pathlib import Path

def progress(directory,stage,step=None,total=None):
    value={'stage':stage,'progress':None,'progress_kind':'stage'}
    if step is not None:value.update(step=step,total_steps=total,progress=round(step/total*100,1),progress_kind='diffusion_steps')
    temporary=directory/'progress.tmp';temporary.write_text(json.dumps(value),encoding='utf-8');temporary.replace(directory/'progress.json')

def run(directory):
    from backend.app.ai3d.contracts import GenerationOptions
    from backend.app.ai3d.mesh import process_glb
    request=json.loads((directory/'request.json').read_text(encoding='utf-8'));options=GenerationOptions.model_validate(request['options'])
    progress(directory,'检查输入与环境')
    if request['engine']=='mock':
        if os.getenv('AI3D_ENABLE_MOCK')!='1':raise RuntimeError('Mock 测试模式未启用')
        import trimesh
        # Deliberately recognizable test geometry, never described as AI inference.
        time.sleep(float(os.getenv('AI3D_MOCK_DELAY','0.2')))
        raw=trimesh.creation.icosphere(subdivisions=2,radius=1).export(file_type='glb')
        progress(directory,'Mock 测试几何（非 AI 推理）')
    else:
        from ai_worker.probe import diagnose
        status=diagnose()
        if not status['available']:raise RuntimeError('；'.join(status['errors']))
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1')
        repo=Path(os.environ['HUNYUAN3D_REPO']).resolve();weights=Path(os.environ['HUNYUAN3D_WEIGHTS']).resolve()
        sys.path.insert(0,str(repo/'hy3dshape'))
        import torch
        from PIL import Image
        from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
        try:
            if request.get('operation')=='texture':
                if not status['texture_ready']:raise RuntimeError('Paint 环境、权重 / 扩展或 21 GiB 显存未准备好；Shape 已保留')
                if not (directory/'shape.glb').is_file():raise RuntimeError('纹理任务缺少已有 Shape')
                progress(directory,'加载独立 Paint 管线（阶段状态，不提供伪造百分比）')
                sys.path.insert(0,str(repo/'hy3dpaint'));os.chdir(repo)
                from textureGenPipeline import Hunyuan3DPaintPipeline,Hunyuan3DPaintConfig
                config=Hunyuan3DPaintConfig(max_num_view=6,resolution=512)
                config.multiview_pretrained_path=str(weights)
                config.multiview_cfg_path=str(repo/'hy3dpaint/cfgs/hunyuan-paint-pbr.yaml')
                config.custom_pipeline=str(repo/'hy3dpaint/hunyuanpaintpbr')
                config.realesrgan_ckpt_path=str(repo/'hy3dpaint/ckpt/RealESRGAN_x4plus.pth')
                dino=os.getenv('HUNYUAN3D_DINO_WEIGHTS')
                if not dino or not Path(dino).is_dir():raise RuntimeError('缺少 Paint 的本地 DINO 权重，禁止自动下载')
                config.dino_ckpt_path=dino
                paint=Hunyuan3DPaintPipeline(config)
                paint(mesh_path=str(directory/'shape.glb'),image_path=str(directory/'reference.png'),output_mesh_path=str(directory/'painted.glb'))
                raw=(directory/'painted.glb').read_bytes();del paint
            else:
                checkpoint=weights/'hunyuan3d-dit-v2-1/model.fp16.ckpt'
                safetensors=(weights/'hunyuan3d-dit-v2-1/model.fp16.safetensors').is_file()
                if not safetensors:
                    from .model_info import CKPT_SHA256
                    progress(directory,'校验已确认下载的官方 checkpoint SHA256')
                    digest=hashlib.sha256()
                    with checkpoint.open('rb') as handle:
                        for chunk in iter(lambda:handle.read(8*1024*1024),b''):digest.update(chunk)
                    if digest.hexdigest()!=CKPT_SHA256:raise RuntimeError('官方 checkpoint SHA256 不匹配，拒绝加载')
                progress(directory,'加载本地 Hunyuan3D 2.1 Shape 权重')
                pipeline=Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(weights),subfolder='hunyuan3d-dit-v2-1',variant='fp16',use_safetensors=safetensors,device='cuda',dtype=torch.float16)
                image=Image.open(directory/'reference.png').convert('RGBA')
                progress(directory,'Shape 扩散采样',0,options.steps)
                def callback(step,t,outputs):progress(directory,'Shape 扩散采样',min(step+1,options.steps),options.steps)
                with torch.inference_mode():
                    mesh=pipeline(image=image,num_inference_steps=options.steps,octree_resolution=options.octree_resolution,guidance_scale=options.guidance_scale,generator=torch.Generator(device='cuda').manual_seed(options.seed),callback=callback,callback_steps=1,enable_pbar=False)[0]
                raw=mesh.export(file_type='glb');del pipeline,mesh
            gc.collect();torch.cuda.empty_cache()
        finally:
            gc.collect()
            if torch.cuda.is_available():torch.cuda.empty_cache()
    (directory/'original.glb').write_bytes(raw)
    progress(directory,'几何验证与 GLB 后处理')
    result,stats=process_glb(raw,options.processing.model_dump())
    if request['engine']!='mock':stats['inference']={key:status.get(key) for key in ('python','torch_version','cuda_version','source_revision','weights_revision')}
    (directory/'model.glb').write_bytes(result);(directory/'stats.json').write_text(json.dumps(stats),encoding='utf-8')
    progress(directory,'完成')

if __name__=='__main__':
    task=Path(sys.argv[1]).resolve()
    try:run(task)
    except Exception as exc:
        (task/'error.json').write_text(json.dumps({'error':str(exc)[:2000],'type':type(exc).__name__}),encoding='utf-8');raise
