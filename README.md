# JobTracker MCP

Track your job search from Claude Code. Two local [MCP](https://modelcontextprotocol.io) servers plus a set of Claude Code skills:

- **`jobtracker`** (`main.py`): scrapes job-posting URLs with [Crawl4AI](https://github.com/unclecode/crawl4ai) into a local SQLite database (`jobtracker.db`), or stores text you paste.
- **`gmail`** (`gmail_mcp.py`): Gmail API wrapper (search, read, label, move, trash, send) used by the skills to file application receipts and rejections.
- **Skills** (`.claude/skills/`): optional workflows that combine the two, e.g. a daily routine that adds today's applications, files confirmation emails and marks rejected jobs.

Everything runs on your machine; your data stays in `jobtracker.db` and your own Gmail account.

## Tools

| Server | Tools |
|---|---|
| jobtracker | `add_job`, `add_job_from_text`, `list_jobs`, `get_job`, `update_job`, `delete_job`, `search_jobs`, `get_stats` |
| gmail | `search_emails`, `list_emails`, `get_email`, `send_email`, `update_labels`, `move_email`, `trash_email`, `get_gmail_stats` |

Job statuses: `new`, `applied`, `interviewing`, `offer`, `rejected`, `archived`. `add_job` always stores `new`; set the real status with `update_job`.

## Setup

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup            # installs the Playwright browser
```

Register the servers (this repo ships a project-scoped `.mcp.json`, so just start Claude Code in this folder). To register them elsewhere, use the venv interpreter directly:

```bash
claude mcp add jobtracker -s project -- .venv/bin/python main.py
claude mcp add gmail -s project -- .venv/bin/python gmail_mcp.py
```

`claude_desktop_config.example.json` shows the same for Claude Desktop (use absolute paths).

> **Do not use `uv run` to launch the servers and keep `fastmcp>=3.4.7,<4`.** Claude Code speaks MCP protocol `2024-11-05`; FastMCP 4.x does not, and the servers show "tools fetch failed / request timed out". Heavy libraries are imported lazily so the servers start in under a second; keep it that way.

### Gmail (optional)

1. In Google Cloud Console create a project, enable the **Gmail API**, configure the OAuth consent screen (add your address as a test user) and create an **OAuth client ID** of type *Desktop app*.
2. Save the downloaded JSON as `gmail_credentials.json` in this folder.
3. Run `.venv/bin/python gmail_mcp.py --auth` and approve access. This writes `.gmail-token.json`.

Both files are git-ignored. Never commit them. Changing the scopes in `gmail_mcp.py` requires deleting the token and authenticating again. If something fails, see the `gmail-mcp-troubleshooting` skill.

## Usage

Ask Claude in plain language, or call the tools directly:

```text
add_job("https://jobs.example.com/senior-engineer")
update_job(job_id, status="applied")
list_jobs(status="applied")
search_jobs("python remote")
```

- LinkedIn and StepStone block scraping via robots.txt and the check is deliberately kept on. Paste the description with `add_job_from_text` instead.
- If a scrape stores blank fields or a thin description, fix it with `update_job`. `add_job` returns warnings describing the problem.
- Extraction understands German-language postings and DACH conventions (Standort, `(m/w/d)`, GmbH/AG, `3.500,00 €`) as well as English ones.
- Back up before bulk changes: `.venv/bin/python scripts/backup_db.py` (one dated copy per day in `backups/`, 30 days kept).

### Daily workflow

Paste the jobs you applied to into `data/todays_jobs.md` (links, or pasted descriptions for Easy Apply jobs) and tell Claude *"update the db with today's jobs"*. The `daily-job-routine` skill adds them, files the confirmation emails and handles rejections.

## Getting started

A typical job hunt from zero to offer:

1. **Profile**: tell Claude *"set up my profile"* (`profile-setup`) or *"build my profile from my resume"* (`profile-from-resume`). It writes `data/profile.md` (and optionally `data/cv.md`), both git-ignored and never leaving your machine.
2. **Collect jobs**: paste links, or descriptions for sites that block scraping, with `add_job` / `add_job_from_text`.
3. **Score**: *"which jobs should I apply to?"* (`job-fit-scorer`) ranks your `new` jobs against the profile as apply / maybe / skip.
4. **Apply**: *"tailor my CV for job X"* (`cv-tailor`) and *"write a cover letter"* (`cover-letter-writer`). Both only reword what your CV really says and list gaps instead of inventing experience.
5. **Track**: set the status with `update_job`. Moving a job to `applied` records `Applied: M/D/YYYY` in its notes; the review and follow-up skills rely on that line.
6. **Follow up**: *"weekly review"* (`weekly-review`) shows the funnel, stale applications and next actions; *"follow up on my applications"* (`followup-outreach`) drafts polite messages. Nothing is ever sent without you saying so.
7. **Interview**: *"prepare me for my interview"* (`interview-prep`) builds a question list and STAR stories from your real experience, and can run a mock interview.

## Skills

### Job-search skills (work without Gmail)

| Skill | Purpose |
|---|---|
| `profile-setup` | interview you and create `data/profile.md` |
| `profile-from-resume` | build the profile from a resume, asking only about the gaps |
| `job-fit-scorer` | score saved jobs 0-100 against your profile, with reasons and the biggest gap |
| `weekly-review` | read-only funnel report, stale applications, 3-5 next actions |
| `cv-tailor` | match table, gap report and a tailored CV draft with a before/after change log |
| `cover-letter-writer` | cover letter plus a short variant, using only facts from your CV |
| `interview-prep` | likely questions, STAR stories, questions to ask, mock interview |
| `followup-outreach` | find applications with no reply and draft follow-ups, referral asks, thank-yous |

They read your private `data/profile.md` and `data/cv.md` and never invent experience. They draft only; nothing is sent, posted or saved to the tracker without your approval. Legal, tax and negotiation content is drafting help, not advice.

## Gmail skills and labels

The skills file mail into labels under one parent label, **`JobApplications`** by default:

| Label | Meaning |
|---|---|
| `JobApplications` | application confirmations |
| `JobApplications/EasyApply` | LinkedIn Easy Apply receipts |
| `JobApplications/Rejected` | rejections |
| `JobApplications/Shortlisted` | positive replies (stay in the inbox, starred) |
| `JobApplications/NeedsAttention` | mail that asks you to do something |

Create these labels in Gmail first. To use another prefix set `JOBTRACKER_LABEL_PREFIX` (for example `export JOBTRACKER_LABEL_PREFIX=Jobs2026`) before running Claude Code. Set `JOBTRACKER_USER_HINTS="yourname,yourdomain.com"` (comma separated) so the classifiers can recognise mail you sent yourself.

| Skill | Purpose |
|---|---|
| `daily-job-routine` | one-shot: add today's jobs, file receipts and rejections, delete job alerts, report what needs you |
| `gmail-job-inbox-triage` | classify the inbox (needs-you, rejection, confirmation, alert) and file the clear cases |
| `gmail-file-applications` | file application confirmations |
| `gmail-file-rejections` | sentence-level rejection classifier and filer |
| `jobtracker-gmail-sync` | update job statuses from Gmail evidence |
| `jobtracker-csv-import` | bulk-import a spreadsheet export |
| `gmail-mcp-troubleshooting` | fix startup, OAuth and quota problems |

Scripts that change anything (database, Gmail labels) default to a dry run and need `--apply`. The classifiers favour precision: when unsure, a mail stays in the inbox. Their sender and phrase lists are tuned for English and German mail. Edit the rules in `.claude/skills/gmail-job-inbox-triage/scripts/triage_rules.py` for your own market.

## Tests

Plain scripts, no pytest; each exits 1 on failure:

```bash
.venv/bin/python scripts/test_job_extract.py
.venv/bin/python scripts/test_applied_date.py
.venv/bin/python .claude/skills/gmail-file-rejections/scripts/test_classifier.py
.venv/bin/python .claude/skills/gmail-file-applications/scripts/test_confirmation.py
.venv/bin/python .claude/skills/gmail-job-inbox-triage/scripts/test_triage.py
```

## Privacy

`jobtracker.db`, `backups/`, `data/` (except the empty template; this includes your `data/profile.md`, `data/cv.md` and every draft the skills save), the Gmail token and credentials are git-ignored. Check `git status` before every commit.

## License

MIT, see `LICENSE`.
