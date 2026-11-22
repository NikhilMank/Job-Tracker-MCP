# scripts/

Helper scripts written while working on this project (data fixes, one-off analysis, Gmail/DB utilities) live
here — **not in the project root**. Reusable, skill-specific tooling lives next to its skill instead:

- `.claude/skills/jobtracker-gmail-sync/scripts/`   fetch Gmail labels, match emails to jobs, apply status changes
- `.claude/skills/gmail-file-rejections/scripts/`   rejection classifier, finder, label mover, tests
- `.claude/skills/jobtracker-csv-import/scripts/`   CSV importer

Conventions: run with `.venv/bin/python` from the project root; default to a dry run and require `--apply`
for anything that writes; back up `jobtracker.db` before writing; never print credentials.
Throw-away intermediate output (downloads, JSON dumps) goes to the session scratchpad, not here.

Backups: never create ad-hoc `jobtracker.db.bak-*` files in the project root. `backup_db.py` (project root: `.venv/bin/python scripts/backup_db.py`) keeps one dated copy per day in `backups/` and prunes anything older than 30 days.
- `tracker_gap.py`  read-only: LinkedIn Easy Apply receipts in Gmail that have no matching job in jobtracker.db (applied but never added)
- `test_job_extract.py`  plain-script tests for `job_extract.py` (scraper field extraction); exits 1 on failure. the tests use small synthetic pages defined inline. To add a regression case from a real page, capture it with `capture_fixture.py` (kept local: `scripts/fixtures/` is git-ignored; do not commit third-party job text).
- `capture_fixture.py`  crawls one job URL like `_scrape_job` pass 1 and stores it in the local `fixtures/job_pages.json` (`NAME URL [--apply]`, dry run by default)
- `setup_check.py`  first-time setup / health check: versions, packages, MCP config, Gmail sign-in and permissions, label structure; dry run by default, `--apply` creates missing labels (used by the `first-time-setup` skill). Tests: `test_setup_check.py`
