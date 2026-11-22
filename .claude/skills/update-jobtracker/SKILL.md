---
name: update-jobtracker
description: Safely update this project to the latest version from GitHub without losing the user's job database, profile, preferences, Gmail sign-in or local edits - back up, show what is new, pull, reinstall dependencies, verify, and ask only the new preference questions. Use when the user says "update the project", "get the latest version", "pull the latest changes", "is there a new version", or "update without losing my settings".
---

# Update JobTracker

Brings a clone of the repo up to date and keeps everything personal. It never discards anything: no `git reset --hard`, no
`git checkout -- .`, no `git clean`, no force push, no deleting files. It asks before the pull and never pushes.

## What an update cannot touch
These are git-ignored, so `git pull` never overwrites them: `jobtracker.db`, `backups/`, everything in `data/` (profile, CV, routine
preferences, daily file, drafts, logs), `gmail_credentials.json`, `.gmail-token.json`, `.claude/settings.local.json`, `.venv/`.
Only **tracked** files can change or conflict: the code, the skills, `.mcp.json`, `.claude/settings.json`, `CLAUDE.md`, docs.
Personal settings therefore belong in the ignored files (`data/...`, `.claude/settings.local.json`), not in tracked ones.

## Steps
1. **Check the situation (read-only).** `git rev-parse --is-inside-work-tree`, `git remote -v`, `git branch --show-current`,
   `git status --short`, `git rev-parse --short HEAD` (remember it: the "before" version).
   - Not a git repo (the user downloaded a ZIP): explain that updating needs a clone. Offer to clone into a **new** folder and copy the
     private items listed above over; do nothing automatically and do not overwrite anything without a go-ahead.
   - No remote, or a different branch than the project's main branch: tell the user what you see and ask how to proceed.
   - List any **modified tracked files** separately (these are local edits, e.g. a customised `triage_rules.py` / `ai_roles.py`).
2. **See what is new.** `git fetch`, then `git log --oneline HEAD..@{u}` (use `origin/main` when no upstream is set) and
   `git diff --stat HEAD..@{u}`. If there is nothing new, say "already up to date" and stop. Otherwise summarise in plain language,
   and call out what matters:
   - `requirements.txt` / `pyproject.toml` changed: dependencies must be reinstalled.
   - `main.py` / `gmail_mcp.py` changed: Claude Code must be restarted (the servers run old code until then).
   - `.claude/skills/**` changed: which skills, in one line each.
   - `routine-preferences.template.md` changed: there may be new preference questions.
   - Anything that touches a file the user edited locally: warn about a possible conflict.
3. **Back up** the database: `.venv/bin/python scripts/backup_db.py` (skip if there is no `jobtracker.db` yet).
4. **Ask** "Update now?" and, if tracked files have local edits, explain the plan: stash them, pull, restore them.
5. **Update.**
   - Clean tree: `git pull --ff-only`.
   - Local edits to tracked files: `git stash push -m "before update"`, `git pull --ff-only`, `git stash pop`. If the pop conflicts,
     show the conflicted files and resolve them **with the user**: keep their edit and the new upstream change where both make sense.
     The stash stays available until the pop succeeds; never drop it.
   - `--ff-only` refuses when the local history diverged: explain, and only then offer `git pull --rebase` after the user agrees.
   - **One-time migration for older clones.** If `git ls-files data/todays_jobs.md` prints the file (earlier versions tracked it; it is
     private and git-ignored now), a plain pull or stash mixes the user's pasted jobs into the new template or aborts. Do exactly this
     (tested): `cp data/todays_jobs.md data/todays_jobs.keep`, check `cmp data/todays_jobs.md data/todays_jobs.keep` succeeds, then
     `git checkout -- data/todays_jobs.md` (the **only** checkout allowed, and only after the `cmp` passed), `git stash push` for any other
     local edits, `git pull --ff-only`, `git stash pop`, and finally `mv data/todays_jobs.keep data/todays_jobs.md`. From then on the file
     is ignored and normal updates need nothing special. Afterwards confirm `git diff -- data/todays_jobs.template.md` is empty.
6. **After the update.**
   - If dependencies changed: `.venv/bin/pip install -r requirements.txt`.
   - Run `.venv/bin/python scripts/setup_check.py` and the project's test scripts (see README, Tests); report failures honestly.
   - **New preference questions:** `setup_check.py` lists preferences that are unanswered, which after an update are the new ones. Ask
     only those (as in `first-time-setup` steps 5-6) and save them into the existing `data/routine-preferences.md`. Never change or
     re-ask answers the user already gave.
   - Tell the user to restart Claude Code (or run `/mcp`) if server code changed.
7. **Report:** old and new version (short hashes), what changed in plain words, what was preserved, what still needs the user, and how
   to go back if something is wrong: the old hash plus the pre-update backup in `backups/`. Do not run a rollback unless asked.

## Rules
- Never print credentials or token contents. Never run anything outside this project folder.
- Never push, force, reset, clean, or delete. If a step would need one of those, stop and explain.
- If a step fails, stop, show the exact error and the state of `git status`; do not retry with something more destructive.
