#!/usr/bin/env python3
"""Bulk-import a job-tracker CSV export (Enhancv-style columns) into jobtracker.db.

Why not the add_job MCP tool?  add_job *scrapes* a URL (slow, LinkedIn blocks it, and it
cannot carry over your statuses).  This writes rows straight into the same table.

Mapping
  Job Position -> title        Company -> company         Location -> location
  Job Description -> description    Type: Remote/Hybrid/On-site -> remote_type remote/hybrid/onsite
  Status: Applied/No answer -> applied (No answer also tagged 'no-answer'),
          Rejected -> rejected, Interviewing -> interviewing, Offer/Accepted -> offer
  Date Applied (else Date Saved) -> scraped_at
  Notes + "Applied: M/D/YYYY" + Salary + Source + Contact -> notes   (the Applied line is
          what the Gmail sync uses for its date check -- keep that exact format)
  tags -> ["<tag>"]   (default csv-import; the Gmail sync filters on it)
URL handling: jobs.url is NOT NULL UNIQUE, so blank URLs become csv-import://row-N and
repeated URLs (genuine re-applications) get a #dupN suffix. Existing URLs are skipped.

  .venv/bin/python import_csv.py data/export.csv            # dry run
  .venv/bin/python import_csv.py data/export.csv --apply    # backs up the DB, then inserts
"""
import argparse, collections, csv, json, os, shutil, sqlite3, time, uuid
from datetime import datetime, timezone

ap = argparse.ArgumentParser()
ap.add_argument("csv_path")
ap.add_argument("--db", default="jobtracker.db")
ap.add_argument("--tag", default="csv-import")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

STATUS = {"rejected": "rejected", "applied": "applied", "interviewing": "interviewing",
          "no answer": "applied", "offer": "offer", "accepted": "offer"}
REMOTE = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite", "": None}


def ts(*dates):
    for s in dates:
        try:
            return int(datetime.strptime(s, "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp())
        except (ValueError, TypeError):
            pass
    return int(time.time())


def backup_database(db_path: str) -> str:
    """Back up via the project's scripts/backup_db.py (one dated copy per day in backups/, prunes copies older than 30 days).
    Never creates ad-hoc jobtracker.db.bak-* files in the project root (see CLAUDE.md)."""
    import subprocess, sys as _sys
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
    if os.path.abspath(db_path) == os.path.join(root, "jobtracker.db"):
        subprocess.run([_sys.executable, os.path.join(root, "scripts", "backup_db.py")], check=True)
        return os.path.join(root, "backups")
    dest = os.path.join(root, "backups", os.path.basename(db_path) + time.strftime("-%Y%m%d-%H%M%S"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy(db_path, dest)
    return dest


rows = list(csv.DictReader(open(args.csv_path, encoding="utf-8-sig")))
db = sqlite3.connect(args.db)
existing = {r[0] for r in db.execute("select url from jobs")}
seen, out, unknown = collections.Counter(), [], collections.Counter()
for i, r in enumerate(rows, 1):
    url = r["URL"].strip() or f"csv-import://row-{i}"
    seen[url] += 1
    if seen[url] > 1:
        url = f"{url}#dup{seen[url]}"
    if url in existing:
        continue
    raw = r["Status"].strip().lower()
    if raw not in STATUS:
        unknown[r["Status"]] += 1
    notes = [x for x in (
        r["Notes"].strip(),
        f"Applied: {r['Date Applied']}" if r["Date Applied"] else "",
        f"Salary: {r['Salary']}" if r["Salary"] else "",
        f"Source: {r['Source']}" if r["Source"] else "",
        f"Contact: {r['Contact']}" if r["Contact"] else "") if x]
    tags = [args.tag] + (["no-answer"] if raw == "no answer" else [])
    out.append((f"job-{uuid.uuid4().hex[:8]}", url, r["Job Position"], r["Company"], r["Location"],
                r["Job Description"], REMOTE.get(r["Type"].strip().lower()),
                ts(r["Date Applied"], r["Date Saved"]), STATUS.get(raw, "applied"),
                "\n".join(notes) or None, json.dumps(tags)))

print(f"{len(rows)} CSV rows -> {len(out)} to insert ({len(rows) - len(out)} already present)")
print("by status:", dict(collections.Counter(o[8] for o in out)))
if unknown:
    print("UNKNOWN statuses (defaulted to 'applied'):", dict(unknown))
if args.apply:
    backup = backup_database(args.db)
    db.executemany("insert into jobs(id,url,title,company,location,description,remote_type,scraped_at,"
                   "status,notes,tags) values(?,?,?,?,?,?,?,?,?,?,?)", out)
    db.commit()
    print("inserted. backups in:", backup)
else:
    print("dry run -- re-run with --apply to write")
