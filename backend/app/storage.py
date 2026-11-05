import os,uuid,shutil
from datetime import datetime,timedelta,timezone

def limits():return {'max_bytes':int(os.getenv('STUDIO_MAX_DISK_MB','2048'))*1024*1024,'retention_days':int(os.getenv('STUDIO_RETENTION_DAYS','30'))}
def folders(root):
    for path in root.iterdir():
        try:valid=str(uuid.UUID(path.name))==path.name
        except ValueError:valid=False
        if valid and path.is_dir() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):yield path
def usage(root):return sum(p.stat().st_size for directory in folders(root) for p in directory.iterdir() if p.is_file() and not p.is_symlink())
def inventory(root,connection):
    with connection() as db:references={r['model_id'] for r in db.execute('SELECT model_id FROM projects WHERE model_id IS NOT NULL')}
    return {**limits(),'used_bytes':usage(root),'assets':[{'id':d.name,'bytes':sum(p.stat().st_size for p in d.iterdir() if p.is_file() and not p.is_symlink()),'protected':d.name in references} for d in folders(root)]}
def cleanup(root,connection,days):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S');removed=[];released=0
    with connection() as db:
        # Hold a write lock across reference checks and file deletion; project saves serialize behind it.
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute("SELECT id FROM jobs WHERE status IN ('completed','failed','cancelled') AND created<=? AND id NOT IN (SELECT model_id FROM projects WHERE model_id IS NOT NULL)",(cutoff,)).fetchall()
        directories={d.name:d for d in folders(root)}
        for row in rows:
            path=directories.get(row['id'])
            if path:
                size=sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink())
                shutil.rmtree(path);released+=size
            db.execute('DELETE FROM assets WHERE id=?',(row['id'],));db.execute('DELETE FROM jobs WHERE id=?',(row['id'],));removed.append(row['id'])
        db.execute('DELETE FROM history WHERE created<=?',(cutoff,))
    return {'removed':removed,'released_bytes':released}
