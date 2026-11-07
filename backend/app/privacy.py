import io,json,sqlite3,tempfile,zipfile,shutil
from contextlib import closing
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from .schema import Strict
router=APIRouter(prefix='/api/privacy')
def core():
    from . import main
    return main
class Delete(Strict):confirmation:str

@router.get('/export')
def export():
    c=core();temporary=Path(tempfile.mkdtemp(prefix='forma-export-'))
    try:
        backup=temporary/'studio.sqlite3';output=temporary/'forma-data.zip'
        with closing(sqlite3.connect(c.DB)) as source,closing(sqlite3.connect(backup)) as target:source.backup(target)
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.write(backup,'studio.sqlite3')
            for path in c.DATA.rglob('*'):
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(c.DATA) and path.suffix in ('.glb','.json','.png','.obj','.mtl'):
                    archive.write(path,path.relative_to(c.DATA).as_posix())
        return FileResponse(output,media_type='application/zip',filename='forma-data.zip',background=BackgroundTask(shutil.rmtree,temporary))
    except Exception:
        shutil.rmtree(temporary);raise

@router.post('/delete')
def delete(request:Delete):
    if request.confirmation!='DELETE ALL LOCAL DATA':raise HTTPException(422,'请输入 DELETE ALL LOCAL DATA 明确确认删除本地项目、资产和历史')
    c=core()
    with c.connection() as db:
        if db.execute("SELECT 1 FROM ai3d_jobs WHERE status IN ('running','pending') UNION SELECT 1 FROM jobs WHERE status IN ('running','pending')").fetchone():raise HTTPException(409,'请先停止活动任务，云端任务可能继续计费')
        db.execute('BEGIN IMMEDIATE')
        for table in ('projects','assets','jobs','history','ai3d_jobs','ai3d_images','library_assets','acceptance_runs'):db.execute('DELETE FROM '+table)
    for path in list(c.storage.folders(c.DATA)):shutil.rmtree(path)
    for name in ('library','backups'):
        path=(c.DATA/name).resolve()
        if path.is_relative_to(c.DATA) and path.is_dir():shutil.rmtree(path)
    return {'deleted':True,'credential_retained':True,'cloud_assets_deleted':False}
