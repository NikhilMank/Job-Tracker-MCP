#!/usr/bin/env python3
"""Back up jobtracker.db to backups/jobtracker-YYYY-MM-DD.db and delete backups older than 30 days.

Run before any write batch, from the project root:  .venv/bin/python scripts/backup_db.py
Same-day runs overwrite that day's file, so there is at most one backup per day.
Uses SQLite's online backup API, so it is safe while the MCP server is running.
Only files directly inside backups/ are ever deleted.
"""
import os
import sqlite3
import sys
import time
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "jobtracker.db")
BACKUP_DIR = os.path.join(ROOT, "backups")
KEEP_DAYS = 30


def main() -> int:
    if not os.path.exists(DB):
        print(f"No database at {DB}", file=sys.stderr)
        return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)

    target = os.path.join(BACKUP_DIR, f"jobtracker-{date.today().isoformat()}.db")
    tmp = target + ".tmp"
    src = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    os.replace(tmp, target)
    print(f"Backed up to {os.path.relpath(target, ROOT)} ({os.path.getsize(target) // 1024} KB)")

    cutoff = time.time() - KEEP_DAYS * 86400
    for name in sorted(os.listdir(BACKUP_DIR)):
        path = os.path.join(BACKUP_DIR, name)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"Deleted old backup {name} (older than {KEEP_DAYS} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
