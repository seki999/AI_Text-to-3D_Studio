"""Backup before upgrading; never automatically downgrade a user's database."""
import sqlite3
from contextlib import closing
from pathlib import Path
SCHEMA_VERSION=4

def prepare(path:Path):
    if not path.exists():return
    with closing(sqlite3.connect(path)) as db:
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version>SCHEMA_VERSION:raise RuntimeError('数据库来自较新版本，请使用新版本应用；禁止自动降级')
        if version<SCHEMA_VERSION:
            backups=path.parent/'backups';backups.mkdir(exist_ok=True)
            target=backups/f'studio-before-v{SCHEMA_VERSION}.sqlite3'
            if not target.exists():
                with closing(sqlite3.connect(target)) as backup:db.backup(backup)

def finish(connection):
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS library_assets(id TEXT PRIMARY KEY,source_id TEXT,description TEXT,provider TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,favorite INTEGER DEFAULT 0,is_mock INTEGER,stats TEXT,bytes INTEGER,metadata TEXT)''')
        db.execute('CREATE TABLE IF NOT EXISTS acceptance_runs(id TEXT PRIMARY KEY,report TEXT NOT NULL)')
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
