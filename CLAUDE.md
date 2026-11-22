# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two independent stdio MCP servers (FastMCP) sharing one project venv, both registered in `.mcp.json` (project scope — tools exist only when Claude Code is started in this directory):

- `main.py` → **jobtracker**: scrapes job-posting URLs with Crawl4AI into a local SQLite DB (`jobtracker.db`). Tools: `add_job`, `add_job_from_text`, `list_jobs`, `get_job`, `update_job`, `delete_job`, `search_jobs`, `get_stats`.
- `gmail_mcp.py` → **gmail**: Gmail API wrapper. Tools: `search_emails`, `list_emails`, `get_email`, `send_email`, `update_labels`, `move_email`, `trash_email`, `get_gmail_stats`.

They do not call each other. Anything that links the two (matching rejection emails to jobs, updating statuses) lives in the skills under `.claude/skills/` and their `scripts/`, which read Gmail output and write `jobtracker.db` directly.

## Commands

```bash
.venv/bin/python main.py                       # run jobtracker server (stdio; Ctrl-C to stop)
.venv/bin/python gmail_mcp.py --auth           # one-time Gmail OAuth login (writes .gmail-token.json)
.venv/bin/python .claude/skills/gmail-file-rejections/scripts/test_classifier.py   # plain test script, exits 1 on failure (see README for all four)
```

No linter, build step, or pytest config exists.

**Always launch with `.venv/bin/python`, never `uv run`** (it re-syncs to FastMCP 4.x and breaks the connection). FastMCP must stay pinned to `>=3.4.7,<4` because Claude Code speaks MCP protocol `2024-11-05`. A "tools fetch failed / Request timed out" error means a server failed to start — use the `gmail-mcp-troubleshooting` skill.

## Architecture notes (non-obvious)

- **Lazy imports are required.** Crawl4AI/Playwright take 6–20 s to import; `main.py` imports them inside `_ensure_crawler()` / `_scrape_job()` only, and the browser starts on the first `add_job`. Never move these imports to module level or add a lifespan that starts the browser — it blocks tool listing and the server times out at startup. Same for the Google client libs in `gmail_mcp.py` (`_ensure_gmail_client()`).
- **Scrape path** (`_scrape_job` → `_normalize_job_data` → `_insert_job`): CSS extraction with `JOB_SCHEMA` first, then `job_extract.py` merges JSON-LD, og:/meta tags (HTML entities decoded) and the page markdown with chrome trimmed (nav above the title, cookie managers, footers, application forms) into title/company/location/salary/description; falls back to raw markdown. A second render pass runs for thin/JS pages. `_scrape_job` runs with `remove_consent_popups` (do **not** add `remove_overlay_elements`: it strips icon headers such as SSF's `location_on` line), `add_job` scrapes at most 4 URLs at a time (`_scrape_sem`; 18 parallel calls once timed one out), and `trim_chrome` cuts share links, 'other jobs' lists, sitemap/© footers and an undismissed consent dialog. Location order: labelled line > field list > icon header > JSON-LD city > CSS > headings/bullets > Job-ID city bullets > postcode block > bare city under the H1 > JSON-LD country code; form labels such as `E-Mail*`/`All` are never locations. Company order: labelled line > JSON-LD > CSS > og/meta > host+page text > `<title>` suffix (`Role - EDAG Group`) > legal-form line above the breadcrumb. Pages that serve only menus/job lists (`nav_only`, e.g. groninger-group.com) make `add_job` fail after the render retry and store nothing: fetch the text elsewhere and use `add_job_from_text`. `trim_chrome` can cut a fact block printed above the posting, so labelled location is also read from the raw page. `add_job` returns `warnings` (blank company/location, description problems) and states the description length; a `!! DESCRIPTION PROBLEM` line means the JD is missing/short/dirty/from an aggregator. **A job description is non-negotiable:** report every such case to the user immediately, fix it in the same run (`update_job(description=...)`), and log it. `add_job_from_text` flags too-short descriptions and pasted LinkedIn/StepStone UI lines. Tests: `.venv/bin/python scripts/test_job_extract.py` (synthetic pages defined inline). `validate_url()` blocks non-http(s), localhost and private IP ranges (SSRF guard) — keep it on any new URL-taking tool.
- **`add_job` always stores `status='new'`** and has no status parameter; set the real status with `update_job` afterwards. `url` is `UNIQUE`; both add tools check for an existing URL first (before scraping) and fail with the existing job's id/status/age unless `allow_duplicate=true`, which stores the job as `url#re-<date>-<id>` (a re-application; servers ignore the fragment, and the scrape still uses the clean URL). Valid statuses: `new, applied, interviewing, offer, rejected, archived` (`VALID_STATUSES`).
- Scraping runs with `check_robots_txt=True`: **stepstone.de and linkedin.com fail with "HTTP 403 - Access denied by robots.txt"**. Do not disable the check or work around it — report those links as failed and ask the user to paste the description for `add_job_from_text`. Do not invent fields for a failed scrape.
- **Every scraper problem is logged** in `data/scraper_failures.md` (add_job error, blank/wrong title/company/location, generic title, shell/cookie/nav description), even when `update_job` fixed it and Firecrawl was not used. See the `daily-job-routine` skill, step 1.
- On sites the CSS schema doesn't match, `add_job` falls back to markdown and stores the job with **blank title/company** (description text is kept). After such an add, read the description and fill the blanks with `update_job(title, company, location, salary)` using only what the page states (salary text is parsed by `_parse_salary`, which handles `3.500,00€` and `$60,000.50`). For bulk loads of existing data use the `jobtracker-csv-import` skill, not repeated `add_job`.
- **Applied date lives in `notes`:** there is no applied-at column. `_with_applied_date()` appends `Applied: M/D/YYYY` (same format as the CSV import) when a job is inserted as `applied` or first moved to `applied` via `update_job`, unless notes already carry one. `weekly-review`, `followup-outreach` and `jobtracker-gmail-sync` read it. `update_job` *replaces* notes and tags, so skills must read the old values and merge. `list_jobs` returns no notes or description; use `get_job`. Test: `scripts/test_applied_date.py`.
- **Job-search skills** (`profile-setup`, `profile-from-resume`, `job-fit-scorer`, `weekly-review`, `cv-tailor`, `cover-letter-writer`, `interview-prep`, `followup-outreach`) keep private data only in git-ignored `data/profile.md` and `data/cv.md`; they draft only and never send, and must not invent experience.
- **First-time setup:** the `first-time-setup` skill + `scripts/setup_check.py` (dry run by default, `--apply` creates missing Gmail labels and `data/`; pure logic tested by `scripts/test_setup_check.py`) verify the install, Gmail permissions and label structure, and collect the preferences below.
- **Mail clean-up is opt-in per user.** `daily-job-routine` section 0a asks once and saves `data/routine-preferences.md` (template `.claude/skills/daily-job-routine/routine-preferences.template.md`). Trashing alerts/letters/notices and filing receipts/rejections run only as those settings say; unset means leave alone and ask. Never hardcode one person's delete rules into a skill or script.
- `tags` is stored as a JSON string in a TEXT column; `posted_date`/`scraped_at` are Unix epoch ints.
- Gmail: label arguments accept names (case-insensitive, e.g. `JobApplications/Rejected`) and are resolved to IDs by `_resolve_label_ids`; system labels and raw IDs pass through. Changing `SCOPES` requires deleting `.gmail-token.json` and re-running `--auth`. Credentials (`gmail_credentials.json`, `.gmail-token.json`) are git-ignored; never print them.
- `jobtracker.db` is git-ignored and irreplaceable. Back it up with `.venv/bin/python scripts/backup_db.py` before any write batch: it writes `backups/jobtracker-YYYY-MM-DD.db` (same-day runs overwrite, so one file per day) and deletes backups older than 30 days. Do not create ad-hoc `jobtracker.db.bak-*` files in the project root.

## Scraper fallback (Firecrawl, optional)

Only applies if you have a Firecrawl MCP connected; otherwise use `add_job_from_text` with pasted text.

`add_job` is always the first attempt for a job URL. Firecrawl (`firecrawl_scrape`) may be used only after `add_job` failed or stored blank title/company, never first, so the failures show what to fix in our scraper. Firecrawl only reads; the job is still stored by our tools: if `add_job` stored a row with blanks, fill it with `update_job`; if `add_job` failed and stored nothing, call `add_job_from_text` with the clean URL and the text Firecrawl returned (only fields the page states, status as needed). Exception: robots.txt 403s (stepstone.de, linkedin.com) are not retried with Firecrawl; ask for pasted text. For every fallback, append one line to `data/scraper_failures.md`: `date | url | add_job error or blank fields | what Firecrawl returned | suspected fix`. Review that file when improving `JOB_SCHEMA` / `_scrape_job`.

## Daily workflow

Jobs applied to are pasted into `data/todays_jobs.md`: links (one URL per line, optional `#tag`s) and, for Easy Apply jobs without a usable link, pasted descriptions (`### Company, Title`, optional URL line, text, `---`). On "update the db with today's jobs": run `scripts/backup_db.py` first; for each link call `add_job` then `update_job(status="applied")`; for each pasted description call `add_job_from_text(..., status="applied")` filling only fields the text states (no scraping, never invent missing ones); report added / duplicate / failed; then **clear `data/todays_jobs.md`**: delete everything under the template headings (links, pasted descriptions, and any `## Done` log) so the file is the empty template again for the next day. First check that every logged job id exists in the database; the database holds the full text, so do not keep raw copies or a Done list in the file. Put the added/duplicate/failed summary in the chat report instead. Strip page chrome from pastes (StepStone match widget with the user's CV name, LinkedIn "Application submitted" lines, recruiter/poster names). **Duplicates:** an exact URL/text match is rejected with the existing job's status and age. If it was added less than 1 day ago, treat it as an accidental double-paste and skip it; if older, it is a re-application, so retry with `allow_duplicate=true`. Never skip silently — list every duplicate and re-application in the report. A same-company/similar-title job with a different link is not blocked; just mention the earlier entry. `add_job_from_text` uses the given URL, or a `manual:<hash>` key (company+title+text) when none. **After the DB update, also file the application confirmation emails** (run the `gmail-job-inbox-triage` skill, or at least `gmail-file-applications`): receipts go to `JobApplications` (LinkedIn Easy Apply also `/EasyApply`), without waiting for another yes. Restart Claude Code after changing `main.py` so the server reloads.


## Configuration (environment variables)
- `JOBTRACKER_LABEL_PREFIX` (default `JobApplications`): parent Gmail label used by all skills.
- `JOBTRACKER_USER_HINTS` (comma separated): substrings identifying your own address/name, so mail you sent is never classified.
- `JOBTRACKER_SWEEP_NOISE`: optional regex for `inbox_sweep.py --hide-noise`.

## Where scripts go
- Helper scripts written during a task go in `scripts/` (see `scripts/README.md`) — never in the project root.
- Skill-specific tooling stays in that skill's `scripts/` folder under `.claude/skills/`.
- Scripts that write (DB, Gmail labels) must default to a dry run, require `--apply`, and back up first.
