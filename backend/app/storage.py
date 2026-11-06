import os,uuid,shutil,json
from datetime import datetime,timedelta,timezone

def limits():return {'max_bytes':int(os.getenv('STUDIO_MAX_DISK_MB','2048'))*1024*1024,'retention_days':int(os.getenv('STUDIO_RETENTION_DAYS','30'))}
def folders(root):
    for path in root.iterdir():
        try:valid=str(uuid.UUID(path.name))==path.name
        except ValueError:valid=False
        if valid and path.is_dir() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):yield path
def usage(root):return sum(p.stat().st_size for directory in folders(root) for p in directory.iterdir() if p.is_file() and not p.is_symlink())
def referenced_assets(db):
    references=set()
    for row in db.execute('SELECT model_id,scene FROM projects'):
        if row['model_id']:references.add(row['model_id'])
        try:
            for obj in json.loads(row['scene']).get('objects',[]):
                asset=obj.get('asset')
                if isinstance(asset,dict) and asset.get('asset_id'):references.add(asset['asset_id'])
        except (ValueError,AttributeError,TypeError):pass
    return references
def inventory(root,connection):
    with connection() as db:references=referenced_assets(db)
    return {**limits(),'used_bytes':usage(root),'assets':[{'id':d.name,'bytes':sum(p.stat().st_size for p in d.iterdir() if p.is_file() and not p.is_symlink()),'protected':d.name in references} for d in folders(root)]}
def cleanup(root,connection,days):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S');removed=[];released=0
    with connection() as db:
        # Hold a write lock across reference checks and file deletion; project saves serialize behind it.
        db.execute('BEGIN IMMEDIATE')
        references=referenced_assets(db)
        has_ai=bool(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai3d_jobs'").fetchone())
        if has_ai:references.update(r['source_job_id'] for r in db.execute("SELECT source_job_id FROM ai3d_jobs WHERE status IN ('pending','running') AND source_job_id IS NOT NULL"))
        rows=db.execute("SELECT id FROM jobs WHERE status IN ('completed','failed','cancelled') AND created<=?",(cutoff,)).fetchall()
        directories={d.name:d for d in folders(root)}
        for row in rows:
            if row['id'] in references:continue
            path=directories.get(row['id'])
            if path:
                size=sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink())
                shutil.rmtree(path);released+=size
            db.execute('DELETE FROM assets WHERE id=?',(row['id'],));db.execute('DELETE FROM jobs WHERE id=?',(row['id'],));removed.append(row['id'])
            if has_ai:db.execute("UPDATE ai3d_jobs SET status='failed',asset_id=NULL,stage='缓存已清理',error='未引用的模型缓存已由用户清理' WHERE asset_id=?",(row['id'],))
        if has_ai:
            stale=db.execute("SELECT id,asset_id FROM ai3d_jobs WHERE status IN ('completed','failed','cancelled') AND created<=?",(cutoff,)).fetchall()
            for row in stale:
                if row['id'] in references or row['asset_id'] in references:continue
                path=directories.get(row['id'])
                if path and path.exists():
                    released+=sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink());shutil.rmtree(path)
                db.execute('DELETE FROM ai3d_jobs WHERE id=?',(row['id'],))
                if row['id'] not in removed:removed.append(row['id'])
            images={r['image_id'] for r in db.execute('SELECT image_id FROM ai3d_jobs')}
            for project in db.execute('SELECT scene FROM projects'):
                try:images.update(o['asset']['source_image'] for o in json.loads(project['scene']).get('objects',[]) if isinstance(o.get('asset'),dict) and o['asset'].get('source_image'))
                except (ValueError,TypeError,KeyError):pass
            for row in db.execute('SELECT id FROM ai3d_images WHERE created<=?',(cutoff,)).fetchall():
                if row['id'] in images:continue
                path=directories.get(row['id'])
                if path and path.exists():released+=sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink());shutil.rmtree(path)
                db.execute('DELETE FROM ai3d_images WHERE id=?',(row['id'],))
                if row['id'] not in removed:removed.append(row['id'])
        db.execute('DELETE FROM history WHERE created<=?',(cutoff,))
    return {'removed':removed,'released_bytes':released}
