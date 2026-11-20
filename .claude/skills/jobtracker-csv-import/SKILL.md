---
name: jobtracker-csv-import
description: Bulk-import a job-tracking CSV export (Enhancv-style columns) into the jobtracker SQLite database with statuses preserved. Use when the user has a CSV/spreadsheet of applications to load into jobtracker, or asks to import, migrate or restore tracker data. Do not use add_job for this.
---

# Import a job tracker CSV into `jobtracker.db`

## Why not `add_job`
`add_job(url)` *scrapes* the page with Crawl4AI: ~1,800 slow scrapes, LinkedIn/Indeed block them,
~17% of rows have no URL, and it can't keep the user's statuses. Insert rows directly instead.

## Steps
1. **Inspect the CSV first** — columns, status values, blank/duplicate URLs, date formats:
   `python3 -c "import csv,collections;r=list(csv.DictReader(open(P,encoding='utf-8-sig')));print(len(r),list(r[0]),collections.Counter(x['Status'] for x in r))"`
2. **Dry run**: `.venv/bin/python scripts/import_csv.py data/<file>.csv` — prints counts by status and
   any UNKNOWN status values (these default to `applied`; map them in `STATUS` if they matter).
3. **Apply**: add `--apply`. It backs the DB up with `scripts/backup_db.py` (one dated copy per day in `backups/`, copies older than 30 days are deleted) and inserts.
   Re-running is safe: URLs already present are skipped.
4. **Verify**: `select status,count(*) from jobs group by status` and compare to the CSV totals.

## Mapping decisions (keep consistent — other skills depend on them)
- Tool statuses are only `new, applied, interviewing, offer, rejected, archived`. CSV "No answer" →
  `applied` + tag `no-answer`.
- `notes` carries `Applied: M/D/YYYY`, Salary, Source, Contact. **Keep the `Applied:` line format** —
  `jobtracker-gmail-sync` parses it for its "email must not predate the application" check.
- Every imported row is tagged `csv-import`; the Gmail sync only considers tagged jobs.
- `url` is NOT NULL UNIQUE → blank URLs become `csv-import://row-N`; repeated URLs (genuine
  re-applications, differing dates) get `#dupN`. Don't dedupe them away.
- Remote type: Remote/Hybrid/On-site → `remote`/`hybrid`/`onsite`. Salary stays free text in notes
  (the numeric salary columns need a currency parser if ever required).

## Next
Run `jobtracker-gmail-sync` to reconcile statuses with Gmail; never bulk-change statuses on keywords.
