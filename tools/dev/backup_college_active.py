"""Read-only online SQLite backup before loading the College upgrade server."""
from pathlib import Path
import sqlite3
from datetime import datetime, timezone, timedelta

root = Path(__file__).resolve().parents[2]
source = root / 'runtime/phase14/player.sqlite3'
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
target = root / 'runtime' / f'before_college_upgrade_{stamp}.sqlite3'
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as live:
    with sqlite3.connect(target) as backup:
        live.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print(target)
