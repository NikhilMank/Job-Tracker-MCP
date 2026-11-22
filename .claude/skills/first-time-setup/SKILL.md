---
name: first-time-setup
description: Guided first-time setup and health check for JobTracker MCP - verifies the environment and MCP servers, checks Gmail sign-in, creates the Gmail label structure if it does not exist, asks the user's preferences (what to do with job alerts, receipts, rejections ...) and saves them. Use when the user has just cloned the repo, says "set up my job tracker", "first time setup", "check my setup", "something is not set up", or when another skill finds a missing label, preference or Gmail sign-in.
---

# First-time setup

One guided pass that leaves the project ready to use and **verified**. Safe to re-run any time (it only changes what is
missing). It asks the user about every choice; it never decides what to delete or move for them.

## Rules
- Ask before every change to the user's Gmail (creating labels) or files (`data/routine-preferences.md`,
  `.claude/settings.local.json`). Show what will change first. Never delete or rename existing labels or mail.
- Never print, open or paste credentials: `gmail_credentials.json`, `.gmail-token.json`. The user performs the Google sign-in
  themselves (README, Setup > B); you only check that the result exists and works.
- Gmail is optional. If the user does not want it, skip every Gmail step and record `gmail_enabled: no`.
- Scripts that write default to a dry run and need `--apply`; `jobtracker.db` is never touched here.
- Report honestly: say what was verified and what could not be (for example "Gmail not signed in yet").

## Steps
1. **Environment check (read-only).** Run `.venv/bin/python scripts/setup_check.py --no-gmail`. Explain every `FAIL` / `TODO` / `WARN`
   in plain words and fix it with the user using the README (Python 3.12+, venv, `pip install -r requirements.txt`, FastMCP `<4`,
   `crawl4ai-setup` only if they want to scrape URLs). Do not continue past a `FAIL`.
2. **MCP servers connected.** Call `get_stats` (jobtracker). If the tool is missing or errors, tell the user to start Claude Code from
   the repo folder, approve the project servers and check `/mcp` (see `gmail-mcp-troubleshooting`). Do not work around it.
3. **Gmail?** Ask: "Do you want Gmail features (file application receipts and rejections, inbox triage)? You can add this later."
   If no: skip to step 7 and save `gmail_enabled: no` in the preferences.
4. **Gmail sign-in.** Run `scripts/setup_check.py` again (it now also checks Gmail). If `gmail_credentials.json` or the token is missing,
   walk the user through README Setup > B (Google Cloud project, Gmail API, consent screen with themselves as test user, Desktop OAuth
   client, `python gmail_mcp.py --auth`, tick **all** checkboxes) and re-run until the token has all three permissions. Then confirm with
   `get_gmail_stats` that the `gmail` server works.
5. **Label structure.**
   - Ask for the parent label name; default `JobApplications`. If they pick another, it must be set for every script: with their approval
     add it to `.claude/settings.local.json` (git-ignored) as `{"env": {"JOBTRACKER_LABEL_PREFIX": "<name>"}}`, merging with any existing
     content, and tell them to restart Claude Code so it takes effect. Until restarted, pass `--prefix <name>` yourself.
   - Also ask for their own name or email domain (so their own sent mail is never mistaken for a rejection) and, with approval, add
     `JOBTRACKER_USER_HINTS` (comma separated, e.g. `jane,jane-doe.com`) to the same `env` block. Optional: they may skip it.
   - Run `scripts/setup_check.py --prefix <name>` and show which labels exist and which are missing. The structure is: `<prefix>`
     (receipts), `<prefix>/Rejected`, `<prefix>/EasyApply` (LinkedIn Easy Apply receipts), `<prefix>/Shortlisted` (positive replies),
     `<prefix>/NeedsAttention` (mail that needs the user), `<prefix>/Attended` (the user marks handled threads). Optional:
     `<prefix>/Accepted` (offers), added with `--with-optional`.
   - If labels are missing, ask "Create these N labels?". On yes run `scripts/setup_check.py --prefix <name> --apply`, then re-run it
     without `--apply` and confirm nothing is missing. Existing labels are never changed.
6. **Preferences.** Ask the questions of `daily-job-routine` section 0a (job-board alerts, employer job letters, "keep my data" mails,
   "application viewed" notices, filing receipts, filing rejections and tracker marking), 2-3 at a time with the options explained,
   recommending the safe answer (`leave` / `no`) without choosing for them. Write `data/routine-preferences.md` from
   `.claude/skills/daily-job-routine/routine-preferences.template.md`, set `gmail_enabled: yes`, print it back and confirm. If the file
   already exists, show it and ask only what they want to change.
7. **Profile.** Offer `profile-from-resume` (they have a CV) or `profile-setup` (interview), or skip for now.
8. **Final verification.** Run `scripts/setup_check.py --prefix <name>` one more time and summarise as a short checklist: environment,
   MCP servers, Gmail (signed in, permissions, labels), preferences saved, profile. Mark each `ready`, `skipped by you` or `still to do`
   with the exact next action. Point to README "Getting started" and mention they can say "change my routine preferences" later.

## Notes
- If a later skill reports a missing label or an unset preference, run only the relevant steps (5 or 6), not the whole pass.
- The same script is the quick health check: when something stops working, run `scripts/setup_check.py` first.
