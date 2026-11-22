# JobTracker MCP

Track your job search from Claude Code. Two local [MCP](https://modelcontextprotocol.io) servers plus a set of Claude Code skills:

- **`jobtracker`** (`main.py`): scrapes job-posting URLs with [Crawl4AI](https://github.com/unclecode/crawl4ai) into a local SQLite database (`jobtracker.db`), or stores text you paste.
- **`gmail`** (`gmail_mcp.py`): Gmail API wrapper (search, read, label, move, trash, send) used by the skills to file application receipts and rejections.
- **Skills** (`.claude/skills/`): optional workflows that combine the two, e.g. a daily routine that adds today's applications, files confirmation emails and marks rejected jobs.

Everything runs on your machine; your data stays in `jobtracker.db` and your own Gmail account.

## Quick start

```bash
git clone https://github.com/NikhilMank/Job-Tracker-MCP.git && cd Job-Tracker-MCP
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && crawl4ai-setup
claude            # approve the project servers, then check /mcp
```

New to this? Follow the numbered [Setup](#setup) below. Gmail is optional and has its own step-by-step guide (including the Google Cloud part).

## Tools

| Server | Tools |
|---|---|
| jobtracker | `add_job`, `add_job_from_text`, `list_jobs`, `get_job`, `update_job`, `delete_job`, `search_jobs`, `get_stats` |
| gmail | `search_emails`, `list_emails`, `get_email`, `send_email`, `update_labels`, `move_email`, `trash_email`, `get_gmail_stats` |

Job statuses: `new`, `applied`, `interviewing`, `offer`, `rejected`, `archived`. `add_job` always stores `new`; set the real status with `update_job`.

## Setup

Two parts: **A. the job tracker** (about 10 minutes, everything you need to save and score jobs) and **B. Gmail** (optional, about 15 minutes, only for the inbox-filing skills). Do A first and ignore B until you want it.

### Before you start

| You need | Check with | Notes |
|---|---|---|
| [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) | `claude --version` | sign in with your own account |
| Python **3.12 or newer** | `python3 --version` | macOS ships an older one: `brew install python@3.12`. Ubuntu/Debian: `sudo apt install python3.12 python3.12-venv` |
| git | `git --version` | |
| Windows | use **WSL2** (Ubuntu) and run everything inside it | the config uses `.venv/bin/python`, which does not exist on native Windows |

### A. Set up the job tracker

**1. Get the code**

```bash
git clone https://github.com/NikhilMank/Job-Tracker-MCP.git
cd Job-Tracker-MCP
```

**2. Create the Python environment and install**

```bash
python3.12 -m venv .venv          # use python3 if that is already 3.12+
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Install the browser used for scraping** (large download, a few hundred MB; skip it if you will only paste job descriptions):

```bash
crawl4ai-setup
```

**4. Start Claude Code in this folder**

```bash
claude
```

The repo ships a project config (`.mcp.json`), so the servers register themselves. Claude Code asks you to approve the project servers the first time: choose to approve `jobtracker` (and `gmail` if you plan to use Part B).

**5. Check that it works**

Run `/mcp` inside Claude Code. `jobtracker` must show **connected**. Then try:

> Add this job: https://example.com/jobs/123   *(use a real posting link)*
> List my jobs.

The first `add_job` is slow (15-30 seconds) because the browser starts then. Your jobs are stored in `jobtracker.db` in this folder.

> If `/mcp` shows `jobtracker` as failed or "tools fetch failed": make sure you launched Claude Code **inside the repo folder**, that `.venv` exists, and that `pip install` finished. More in [Troubleshooting](#troubleshooting).

Done with Part A. Continue with [Getting started](#getting-started) to build your profile, or do Part B first.

> **Do not launch the servers with `uv run`, and keep `fastmcp>=3.4.7,<4`.** Claude Code speaks MCP protocol `2024-11-05`; FastMCP 4.x does not, and the servers show "tools fetch failed / request timed out".

**Other setups:** to register the servers from another folder use the venv interpreter with absolute paths, e.g. `claude mcp add jobtracker -s user -- /abs/path/.venv/bin/python /abs/path/main.py`. `claude_desktop_config.example.json` shows the same for Claude Desktop.

### B. Set up Gmail (optional)

Gmail access needs your own Google Cloud OAuth client: nobody else's app ever sees your mail, and the token stays on your machine. It is free.

**1. Create a Google Cloud project**
1. Open <https://console.cloud.google.com/> and sign in with the Gmail account you want to use.
2. Click the project picker at the top, then **New project**. Name it e.g. `jobtracker` and click **Create**. Make sure it is selected afterwards.

**2. Enable the Gmail API**
1. Menu **APIs & Services > Library** (or search "Gmail API" in the top search bar).
2. Open **Gmail API** and click **Enable**.

**3. Configure the consent screen** (Google calls this *Google Auth Platform*, older consoles say *OAuth consent screen*)
1. Menu **APIs & Services > OAuth consent screen**, then **Get started**.
2. App name: `jobtracker`. User support email: your address. Click **Next**.
3. Audience: choose **External**. Click **Next**.
4. Contact email: your address. Accept the policy and click **Create**.
5. Open **Audience** and, under **Test users**, click **Add users** and add **your own Gmail address**. Without this, sign-in fails with `Error 403: access_denied`.

**4. Create the OAuth client and download it**
1. Open **Clients** (older consoles: **Credentials > Create credentials > OAuth client ID**) and click **Create client**.
2. Application type: **Desktop app**. Name: anything. Click **Create**.
3. Click **Download JSON** on the confirmation dialog.
4. Move the file into the repo folder and rename it exactly **`gmail_credentials.json`**.

**5. Sign in once**

Run this in a normal terminal (not through Claude), inside the repo folder:

```bash
source .venv/bin/activate
python gmail_mcp.py --auth
```

1. It prints a long URL. Open it in your browser and choose your account.
2. Google warns that the app is not verified (normal for your own test app): click **Advanced > Go to jobtracker (unsafe)**.
3. **Tick every permission checkbox** (read, send, modify) and continue. Unticked boxes are silently dropped and later calls fail with "insufficient authentication scopes".
4. The browser then shows **"localhost refused to connect"**. That is expected. Copy the **full URL from the address bar** (it starts with `http://localhost:8765/?state=...&code=...`), paste it into the terminal and press Enter.
5. `.gmail-token.json` is created. Keep the terminal open until it says the token was saved; the code in the URL is single-use.

**6. Choose and create labels (optional).** The easiest way: start Claude Code and say *"set up my job tracker"*; the `first-time-setup` skill checks everything, asks which label features you want, creates only those (after asking you) and saves your preferences. Or create the ones you want yourself in Gmail (left sidebar > **+** next to Labels), or run `python scripts/setup_check.py --labels rejected,shortlisted --apply`. All labels the skills can use:

`JobApplications` (filed receipts, also the parent of the others), `JobApplications/Rejected`, `JobApplications/EasyApply`, `JobApplications/Shortlisted`, `JobApplications/NeedsAttention`, `JobApplications/Attended`, `JobApplications/Accepted`. Create only the ones for features you want. To use another prefix set `JOBTRACKER_LABEL_PREFIX` (see [Gmail skills and labels](#gmail-skills-and-labels)).

**7. Reconnect and test.** Restart Claude Code (or run `/mcp`), confirm `gmail` is connected and ask: *"How many emails are in my inbox?"* (`get_gmail_stats`).

Good to know:
- While the OAuth app is in **Testing** mode, Google expires the token after **7 days**; just run `python gmail_mcp.py --auth` again. To stop that, open **Audience** and set **Publishing status: In production** (it stays "unverified", which is fine for a personal app).
- `gmail_credentials.json` and `.gmail-token.json` are secrets. They are git-ignored; never commit, share or paste them.
- Claude Code with the `gmail` server can read, label, move, trash and **send** mail. Skills only do what you approve, but review what Claude proposes.
- Headless/WSL: if the browser cannot open from the terminal, copy the URL into a browser on your normal desktop; the flow above works unchanged.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `jobtracker` or `gmail` shows failed / "tools fetch failed / request timed out" | check `.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"` prints `3.x`; delete stale bytecode `find . -name "*.pyc" -not -path "./.venv/*" -delete`; run `/mcp` to reconnect |
| `/mcp` does not list the servers | start `claude` from inside the repo folder and approve the project servers when asked |
| First `add_job` is very slow or errors about a browser | run `crawl4ai-setup`; the first call starts the browser |
| LinkedIn/StepStone link fails with `HTTP 403 ... robots.txt` | expected: copy the job text and use `add_job_from_text` |
| `Error 403: access_denied` at Google sign-in | add your address under **Audience > Test users** and confirm the Gmail API is enabled |
| "Gmail is not authorized" | run `python gmail_mcp.py --auth` (Part B step 5) |
| "insufficient authentication scopes" | delete `.gmail-token.json`, run `--auth` again and tick **all** checkboxes |
| Gmail worked, now fails after about a week | Testing-mode token expired: run `--auth` again |
| "Quota exceeded" | wait a few minutes; the skills batch requests to avoid it |

The `gmail-mcp-troubleshooting` skill covers these and more: ask Claude *"my gmail server fails"*.

### Updating to the latest version

Your own data is safe: `jobtracker.db`, `backups/`, everything in `data/` (profile, CV, saved preferences, daily file), your Gmail
credentials and token, and `.claude/settings.local.json` are **git-ignored**, so updating never overwrites them. Only tracked files
(code, skills, docs) change. Keep your personal settings in those ignored files rather than editing tracked ones.

**Easiest: ask Claude.** Start Claude Code in the repo folder and say *"update the project to the latest version"*. The `update-jobtracker`
skill backs up your database, shows what is new, asks before pulling, keeps any local edits, reinstalls dependencies if needed, runs the
checks, and asks you **only the new preference questions**, never the ones you already answered. It never discards anything.

**By hand:**

```bash
cd Job-Tracker-MCP
source .venv/bin/activate
python scripts/backup_db.py             # safety copy of your jobs (keeps one per day)
git status                              # only "untracked/ignored" files? then you are clean
git pull --ff-only                      # fetch and apply the latest version
pip install -r requirements.txt         # only if requirements.txt changed
python scripts/setup_check.py           # health check; also lists any new, unanswered preference questions
```

Then restart Claude Code (or run `/mcp`) so the servers load the new code, and say *"check my setup"* to answer any new preference questions.

- **You edited tracked files** (for example `triage_rules.py`)? `git pull` may refuse. Run `git stash`, then `git pull --ff-only`, then `git stash pop`, and fix any conflict it reports (Claude can help). Do **not** use `git reset --hard`, `git checkout .` or `git clean`: those throw your edits away.
- **You downloaded a ZIP** instead of cloning? Updating needs git. Clone the repo into a new folder, then copy `jobtracker.db`, `backups/`, `data/`, `gmail_credentials.json`, `.gmail-token.json` and `.claude/settings.local.json` from the old folder into the new one.
- **You forked the repo?** Add this repository once as `upstream` (`git remote add upstream https://github.com/NikhilMank/Job-Tracker-MCP.git`), then `git fetch upstream` and `git merge upstream/main`.
- **Something broke after updating?** Your database copy is in `backups/`; to go back to the previous version find its hash with `git reflog` and ask Claude to help you return to it safely.

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

Paste the jobs you applied to into `data/todays_jobs.md` (created from `data/todays_jobs.template.md` on first use, and git-ignored; links, or pasted descriptions for Easy Apply jobs) and tell Claude *"update the db with today's jobs"*. The `daily-job-routine` skill adds them, files the confirmation emails and handles rejections.

## Getting started

A typical job hunt from zero to offer:

0. **Set up and verify** (once): tell Claude *"set up my job tracker"* (`first-time-setup`). It checks your install, Gmail sign-in and labels, creates missing labels, asks what the daily routine may delete or move, and saves your answers.
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

The skills can file mail into labels under one parent label, **`JobApplications`** by default. **Every label is optional**: the setup asks which features you want and creates only those labels. Without a label, the matching mail is still classified and reported, just not labelled or moved.

| Label | Meaning |
|---|---|
| `JobApplications` | application confirmations |
| `JobApplications/EasyApply` | LinkedIn Easy Apply receipts |
| `JobApplications/Rejected` | rejections |
| `JobApplications/Shortlisted` | positive replies (stay in the inbox, starred) |
| `JobApplications/NeedsAttention` | mail that asks you to do something |
| `JobApplications/Attended` | you add it to threads you have dealt with; the routine stops reminding you |

The `first-time-setup` skill creates the labels you choose (or run `python scripts/setup_check.py --labels rejected,shortlisted --apply`). To use another prefix set `JOBTRACKER_LABEL_PREFIX` (for example `export JOBTRACKER_LABEL_PREFIX=Jobs2026`) before running Claude Code. Set `JOBTRACKER_USER_HINTS="yourname,yourdomain.com"` (comma separated) so the classifiers can recognise mail you sent yourself.

| Skill | Purpose |
|---|---|
| `update-jobtracker` | update to the latest version without losing your data, settings or local edits; asks only the new preference questions |
| `first-time-setup` | verify the install and Gmail, create missing labels, ask and save your preferences (re-runnable health check) |
| `daily-job-routine` | one-shot: add today's jobs, file receipts and rejections, delete job alerts, report what needs you |
| `gmail-job-inbox-triage` | classify the inbox (needs-you, rejection, confirmation, alert) and file the clear cases |
| `gmail-file-applications` | file application confirmations |
| `gmail-file-rejections` | sentence-level rejection classifier and filer |
| `jobtracker-gmail-sync` | update job statuses from Gmail evidence |
| `jobtracker-csv-import` | bulk-import a spreadsheet export |
| `gmail-mcp-troubleshooting` | fix startup, OAuth and quota problems |

**Nothing is deleted or moved by default.** The first time you run the daily routine, Claude asks what to do with each kind of mail (job-board alerts, employer job letters, "keep my data" mails, receipts, rejections) and saves your answers in `data/routine-preferences.md` (git-ignored). Say *"change my routine preferences"* to edit them. Trash always means Gmail's Trash with an undo log, never a permanent delete.

Scripts that change anything (database, Gmail labels) default to a dry run and need `--apply`. The classifiers favour precision: when unsure, a mail stays in the inbox. Their sender and phrase lists are tuned for English and German mail. Edit the rules in `.claude/skills/gmail-job-inbox-triage/scripts/triage_rules.py` for your own market.

## Tests

Plain scripts, no pytest; each exits 1 on failure:

```bash
.venv/bin/python scripts/test_job_extract.py
.venv/bin/python scripts/test_applied_date.py
.venv/bin/python scripts/test_setup_check.py
.venv/bin/python .claude/skills/gmail-file-rejections/scripts/test_classifier.py
.venv/bin/python .claude/skills/gmail-file-applications/scripts/test_confirmation.py
.venv/bin/python .claude/skills/gmail-job-inbox-triage/scripts/test_triage.py
```

## Privacy

`jobtracker.db`, `backups/`, `data/` (except the template files; this includes your `data/profile.md`, `data/cv.md` and every draft the skills save), the Gmail token and credentials are git-ignored. Check `git status` before every commit.

## License

MIT, see `LICENSE`.
