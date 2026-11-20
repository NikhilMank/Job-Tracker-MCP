---
name: daily-job-routine
description: The user's one-shot daily job routine - add today's applied jobs to jobtracker.db from data/todays_jobs.md, file the application confirmation emails into JobApplications, file rejection emails into JobApplications/Rejected and mark those jobs rejected, trash job-site alerts and company job letters (company letters that list a full-time AI role are kept and reported), and report mail that needs the user. Use when the user says "do my daily job update", "update today's jobs", "update the new jobs", "sort my inbox after updating the tracker" or asks for the whole routine.
---

# Daily job routine

Runs four jobs in one pass. It reuses the existing skills; this file only fixes the order, the permissions and the report.
Nothing here runs on a schedule - only when the user asks.

| # | Job | Reused from |
|---|-----|-------------|
| 1 | Add today's applied jobs to the DB | project `CLAUDE.md` -> "Daily workflow" |
| 2 | File confirmation emails -> `JobApplications` | `gmail-job-inbox-triage` (C, E), `gmail-file-applications` |
| 3 | File rejections -> `JobApplications/Rejected`, mark the jobs `rejected` | `gmail-file-rejections`, `jobtracker-gmail-sync` |
| 4 | Trash job-site alerts and company letters without an AI role; report company-letter AI roles only | `gmail-job-inbox-triage` (A, B) + `--report-ai` / `--trash-no-ai` |
| 4b | Update the notes on ongoing interviews (`data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist)) every run | step 5a3 |
| 5 | Tell the user what needs them | report below |

Principle (from `gmail-job-inbox-triage`): **precision over recall.** Hiding a real mail is worse than leaving a receipt in the
inbox. Settle doubtful mail yourself by reading it; never hand the user a verification list. Everything "deleted" is Trash with an
undo log, never permanent. Run from the project root with `.venv/bin/python`; scratch files go in the session scratchpad, helper
scripts in `scripts/`.

## 0. Prepare
- `jobtracker` and `gmail` MCP tools must be connected. If ToolSearch says CONNECT_TIMEOUT, tell the user to run `/mcp` (cold start from
  a project on a Windows drive mounted in WSL (`/mnt/...`) can exceed 30 s) - do not work around it. See `gmail-mcp-troubleshooting`.
- Read `data/todays_jobs.md` (do not rely on the user saying they applied or not). If it is the empty template, skip step 1 **and the
  up-front backup** and say so. Otherwise run `.venv/bin/python scripts/backup_db.py` before adding jobs.
- Step 3's status updates (marking jobs `rejected`) still take their own backup right before the first write; skip it only if the user says so.

## 1. Update the DB (follow CLAUDE.md "Daily workflow" exactly)
- Links: `add_job` then `update_job(status="applied")`. Pasted blocks: `add_job_from_text(..., status="applied")`, filling only what the
  text states; strip page chrome and recruiter names. `allow_duplicate=true` only for a re-application (existing entry older than a day).
- Before adding a pasted block, `search_jobs` for the same company + title added **less than a day ago**: that is an accidental double
  paste, skip it (the manual text hash differs when the paste is trimmed differently, so the tool will not catch it).
- Scrapes that fail or come back blank (Workday and similar JS pages): `add_job` is always tried first. Only then fall back to
  `firecrawl_scrape` on the clean URL, then store it with our tools: `update_job(title, company, location)` if `add_job` left a blank row, or `add_job_from_text(url=clean URL, ...)` if `add_job` stored nothing (status `applied`). Never invent fields.
  robots.txt 403s (stepstone, linkedin) are not retried with Firecrawl: report them and ask for pasted text. A page that stays unreadable: report it.
- **Log every scraper problem, not only Firecrawl fallbacks**: after the links are added, compare each
  stored row with the page (`get_job`) and append one line to `data/scraper_failures.md` for every link where `add_job` errored, stored a blank or
  wrong title/company/location, stored a generic title ("JobPortal", "Jobs"), or stored a shell/cookie/navigation description - whether or not
  Firecrawl was used and whether you fixed it with `update_job`. Format: `date | url | what was blank/wrong | what Firecrawl returned or "not needed, filled from page text" | suspected fix` (name where the page states the value). Do this in the same run, before the report; the log is how `JOB_SCHEMA` / `_scrape_job` get improved. Count clean scrapes vs problems in the report (step 5, DB update).
- **A job description is non-negotiable.** Every `add_job` / `add_job_from_text` reply states `description N chars`. A line `!! DESCRIPTION PROBLEM` (or `description_ok: false`, or a `description ...` entry in `warnings`) means the JD is missing, short, still has cookie/footer/navigation text, comes from an aggregator, or a paste still has LinkedIn/StepStone UI lines. Tell the user about EVERY such case at the top of the report, never only in the scraper log, and do not finish the run with a job that has no usable JD: find the real text (employer page first, then `firecrawl_scrape`, else ask for a paste), fix it with `update_job(description=...)`, and say which source it came from. Also check the stored text yourself with `get_job` for jobs from sites with known trouble. Jobs without any JD found are listed by id as "NO JOB DESCRIPTION".
- `add_job` now ends its reply with `[check: ...]` when its own quality check found something (company/location blank, cookie/footer text left in the description): treat each as a scraper problem for the log above.
- Verify every new id exists and has a title and company, then reset `data/todays_jobs.md` to the empty template (CLAUDE.md).
- Report added / duplicate / re-application / failed.

## 2 + 3. Triage the inbox, file receipts and rejections
1. `gmail-job-inbox-triage/scripts/triage_inbox.py --out <scratch>/triage` (read-only; add `--since all` only if rules changed).
2. **Needs-you** (`NEEDS_YOU`): stays in the inbox, goes first in the report. A reminder for a step the user has already done
   (e.g. a personality test they confirm is finished) may be filed once they say so. **Mail the user has labelled
   `JobApplications/Attended` is already dealt with**: `triage_inbox.py` skips it and prints only a
   count. Do not repeat it as a reminder; in the report mention it only as one line ("N mails already dealt with, not repeated").
   Never move or relabel it; only the user adds that label. The user labels whole threads in Gmail (labels cannot be put on a single
   mail there), so `Attended` covers the conversation as it was when they labelled it. A **later reply** in that thread must still reach
   the user, and it does by itself. A reply to an `Attended` thread, from the same sender or anyone
   else, is therefore ordinary new mail: triage it normally and report it as a new reply. Only mail that was already in the thread when
   the user labelled it is skipped. No manual thread check is needed.
   Every other needs-you mail gets the label `JobApplications/NeedsAttention` (add it only, Inbox untouched, no new script); the
   user then adds `Attended` when done. **Clean up the pair every run**: search
   `label:JobApplications/NeedsAttention label:JobApplications/Attended` and remove `NeedsAttention` from every hit
   (`update_labels(remove_labels="JobApplications/NeedsAttention")`, nothing else touched), because the user has dealt with it.
   Mention the count in one line. A mail that is only `NeedsAttention` (no `Attended`) keeps the label and stays in the report.
3. **Rejections**: first run the **shortlist gate** on every `REJECTION` mail, before anything is moved: match it to its job (company + title, `search_jobs`) and check whether that job is `interviewing`/`offer`, has a section in `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist), or the same company has a mail labelled `JobApplications/Shortlisted`. A hit is a **withdrawal after shortlisting**: remove it from `rejected.json`; it stays in the inbox with `JobApplications/NeedsAttention` (add it with `move_emails.py --to JobApplications/NeedsAttention --remove JobApplications/Rejected --also-add INBOX --also-add JobApplications/Shortlisted` only if it was already moved), the tracker is NOT set to `rejected`, and it is reported under "Needs you" (step 5a has the notes handling). The user usually wants to reply first; file it only when they say so or a week has passed with no answer. A company's interview cancellation mail ("Abgesagtes Ereignis", "interview cancelled") counts as the same event. Then file the remaining rejections with `gmail-file-rejections/scripts/move_emails.py --ids rejected.json --to JobApplications/Rejected --apply`.
4. **Receipts** (`CONFIRM`, `CONFIRM_EASY`, and `DOUBTFUL` mails you read and found to be plain acknowledgements): file with
   `--to JobApplications` (Easy Apply: `--also-add JobApplications/EasyApply`, LinkedIn only). An acknowledgement that
   only adds a candidate satisfaction survey is still a receipt - file it. **A mail with a "confirm your email" / "click to complete
   your application" button is NOT a receipt**: the application is incomplete until the user clicks it, so it stays in the inbox
   and goes first in the report (file it only after the user says they confirmed). The same holds for any real request
   (documents, a test not yet taken, a questionnaire that is part of the process, an interview invitation).
5. Do not wait for another yes on high-confidence items; the user asked for the sort.
5a. **Positive replies (`SHORTLISTED`)** - standing rule: star the mail, add the label `JobApplications/Shortlisted`, KEEP it in the inbox (`gmail-job-inbox-triage/scripts/mark_shortlisted.py`). **If the mail also asks the user to do something** (pick or confirm an appointment, accept a rescheduled time, reply, take a test), also add `JobApplications/NeedsAttention` (`update_labels(add_labels=...)`, user rule, 2026-11-03, act legal): a shortlisted mail with an open action is needs-you as well, so it carries both labels. Then update the tracker (`interviewing` / `offer`) when company and title match. Also add or update the job's section in `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist) (timeline, open steps) **and pull the job description**: copy the full text from the tracker (`get_job`) into `data/<company>_interview.md` (header with id/status/posting, invitation details, then the full description; see `data/sonar_interview.md`) and link it from the section. If the stored description is empty, say so in the report and fix it with `update_job(description=...)`. **If the job is not in the tracker at all (applied via Easy Apply and never pasted), do not wait for a paste:** find the posting yourself (company career site first, else `firecrawl_search` for the exact title + company, aggregators like BeBee/Glassdoor are fine), `add_job` it (our scraper first), set the status, trim page chrome with `update_job(description=...)`, then write the `data/<company>_interview.md` file. **German postings get an English version:** if the job description is in German, keep the original text and append a section `## English version` at the very bottom of `data/<company>_interview.md` with a faithful, complete English translation of the description (all duties, requirements, benefits; nothing summarised or invented; keep technical terms and the job title as written). English postings need no extra section. Say in the report which source the text came from. **A company that withdraws or rejects AFTER shortlisting is NOT filed as a normal rejection:** keep the mail in the inbox with `Shortlisted` + `JobApplications/NeedsAttention`, leave the tracker at `interviewing` with a note, keep the section in `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist) (open step: user replies, re-check after a week), and only after the user says so, or a week passes with no answer or a final no, set `rejected`, file the mail to `Rejected` and close the section. Report it under "Needs you", not "Rejections". For other closings (offer declined, user withdrew, final rejection), set the tracker to `rejected` (or the matching status) and move its section from `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist) to `data/shortlisted_closed.md` with the closing date and reason. Automated assessment/test mails (ELIGO, personality tests, Continental Online Assessment, ...) are NOT shortlisted, but they ask the user to act: add `JobApplications/NeedsAttention`, keep them in the inbox and report the deadline.
5a2. **`STALE_PROFILE` mails** ("your profile will be deleted for inactivity - log in") - standing permission: trash them with `trash_emails.py` (dry run, then `--apply`) and list them in the report.
5a3. **Update the notes on ongoing interviews every run, even when no new positive reply arrived.** Read `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist) and, for every active section (one section per company you are interviewing with), look at the newest mails of its Gmail thread **in both directions, inbox AND Sent**. Run `gmail-job-inbox-triage/scripts/company_thread.py <Company> [<Company> ...] --days 45 --text` (read-only; lists received and SENT mail oldest first with attachments). A task counts as open only if neither a received nor a sent mail shows it done; never write "no sent mail seen" without having run this (`search_emails` on the company name / `label:JobApplications/Shortlisted` as before; the triage lists them as `UNCLASSIFIED`: calendar invites, cancellations, "Re:" replies, reschedules). Add each new event to the section's Timeline with its date (interview booked / moved / cancelled / held, replies from either side, tasks promised or sent), tick or add Open / next steps, and flag steps whose date has passed or whose wait period ended (e.g. the one-week wait after a withdrawal). Write only what the mails state; if a date or time is only in a calendar attachment, or you cannot tell whether an interview took place or how it went, say so in the note and ask the user. Then set the tracker status only on evidence, as in 5a. Do this before the report and list what changed under "Positive replies / ongoing interviews".
5b. **Read every `DOUBTFUL` and `UNCLASSIFIED` mail** (bodies are in `<scratch>/triage/bodies.json`) and settle it: plain receipt -> file, rejection -> file + mark job, interview/assessment/draft/profile request -> `NEEDS_YOU` (report first; set the job `interviewing` only when the mail names company **and** title). Never leave a job-related mail unaccounted for.
5c. **Verification pass after filing:** re-run `triage_inbox.py --since 14 --out <scratch>/triage_check`. Whatever is still listed must be a mail you deliberately left (needs-you, or a status update) and must appear in the report. If the user later names a mail you missed, follow the "Gotchas" in `gmail-job-inbox-triage/SKILL.md`.
5d. **Inbox sweep.** `triage_inbox.py` can miss mail (rules that return nothing, mail missing from its download). After filing, list **every mail in `in:inbox newer_than:21d`** straight from Gmail with `gmail-job-inbox-triage/scripts/inbox_sweep.py --days 21 --hide-noise` (From/Subject/Date only, `NA` = NeedsAttention; run in the background if slow; not parallel MCP calls; do not write throwaway sweep scripts into the scratchpad, they vanish between sessions) and go through the list yourself. Anything job-related that is not a deliberately kept mail (needs-you, shortlisted thread, held company letter, gig outreach) is handled in the same run: consent / data-retention / "keep my data" mail and talent or job newsletters -> trash (`trash_emails.py`); portal-account-created mails, feedback surveys and receipts -> `JobApplications`; assessment / interview / reschedule mails -> `NeedsAttention` and into the notes (5a3). Then add the missed pattern to `triage_rules.py` / `clean_job_suggestions.py` with a regression case (`test_triage.py`) and say in the report which rule was added. Non-job mail (shopping, banking, newsletters unrelated to the job search) is not touched; mention only a count.
6. **Mark rejected jobs in the DB** (not the withdrawn-after-shortlisting jobs from step 3; those stay `interviewing` with a note) (`jobtracker-gmail-sync` evidence standard: company **and** title must match; settle ambiguity from
   evidence: most recent `applied` entry; if the same posting is in the tracker twice, close both; leave older, already-closed entries).
   `update_job(status="rejected", notes="Rejected per email <date> (gmail:<id>)")`. Skip jobs already `rejected`.
7. Commit: `triage_inbox.py --out <scratch>/triage --no-fetch --commit`.

## 4. Job letters (standing permission to trash)
The user has authorised this for this skill (it overrides the old "wait for the go-ahead" rule): job-site alerts are always trashed; company letters are trashed unless they list a full-time AI role.
- Job-site alerts (LinkedIn/Stepstone/Glassdoor/XING/jobvector/Instaffo...): **always trashed, AI role or not** - the user never opens
  them. `clean_job_suggestions.py --out <scratch>/sugg --report-ai` (dry run), look at WOULD TRASH / KEPT, then the same with
  `--apply`. `--report-ai` reads the bodies and lists the full-time AI roles seen in the alerts before they are trashed (use
  `--hold-ai` instead only if the user asks to keep alerts that have an AI role). Recoverable from Trash for ~30 days.
- Company job-agent letters (SuccessFactors/jobs2web etc.): `scan_company_jobletters.py --out <scratch>/cjl --trash-no-ai`.
  It trashes only letters without a full-time AI role and prints the others. Run `--since all` first if this is the first run with a
  new rule. Letters carry no links: the user finds the role on the company's career site.
- "Your application was viewed by X" notices (LinkedIn, Stepstone, Indeed, ...) are trashed too (rule `application viewed notice`): they
  mean nothing until the company answers. A real answer or a "message from <company>" notice stays protected and is reported.
- Protected mail (application receipts/updates, recruiter messages, invitations, billing/security) is never trashed.
- **Alerts are just deleted: never list or summarise roles from LinkedIn/Stepstone/Glassdoor/XING/jobvector alerts in the report**. Run `clean_job_suggestions.py` without `--report-ai` and mention only the count.
- "Zwischenstand"/status-delay mails ("selection is delayed") from a company whose confirmation is already in `JobApplications` are useless: trash them (search `<company> label:JobApplications` first).
- **Read the AI-role list yourself (company letters held only, never alerts)** and write a clean list: company, role title, location, salary if shown, mail date, sender + subject
  (so the user can find it in Gmail). Drop duplicates across mails, drop roles already in `jobtracker.db` (check with `search_jobs`),
  drop internships/thesis/working-student roles. Roles that are only `Data Engineer`-type are "related": list them separately.
  The raw segments printed by the scripts are noisy and glue neighbouring titles; do not paste them.

## 5. Report (in this order, short)
0. **Ongoing interviews** - one line per active section of `data/shortlisted.md` (optional, your own interview notes; skip this step if the file does not exist) saying what the notes update (step 5a3) changed, and what is still open or overdue (interview held but outcome unknown, task owed, wait period over).
0b. **Positive replies** - each shortlisted mail (starred + labelled, still in the inbox) with company, role and what is asked (e.g. book a slot), and the tracker status you set.
1. **Needs you** - each mail with sender, date, deadline and what is asked (interview invitations, assessments with deadlines, draft/incomplete applications, profile requests).
2. **AI full-time roles found in company job letters** (still in Gmail) - table: company, role, location/salary, date, where to find it in Gmail. Nothing from alerts; skip the section if there are no held letters.
3. **Rejections** filed, each with its deciding sentence, and the jobs marked `rejected` (ids). Withdrawals after shortlisting are NOT listed here but under item 1 (Needs you).
4. **DB update** - added / duplicates / re-applications / failures, and EVERY job whose description had a problem (id, what was wrong, what you did, source of the final text).
5. **Receipts** filed (counts) and the doubtful ones settled.
6. **Trashed** (counts per source + undo-log paths in `data/trashed_emails_log/`), and which company letters stay because they list an AI role.
7. Anything where you made a judgement call (e.g. which duplicate entry you closed).
Say that cleanup removes only what exists now; alerts keep arriving.

## Undo
`move_emails.py --undo data/moved_emails_log/<file>.json`; trash: `clean_job_suggestions.py --undo data/trashed_emails_log/<file>.json`.
Restore `jobtracker.db` from `backups/jobtracker-YYYY-MM-DD.db` only if the user asks.

## Improving
Fix causes where they live (classifier wording, `RULES`/`PROTECT` in `clean_job_suggestions.py`, `NONFT`/`CORE` in
`gmail-job-inbox-triage/scripts/ai_roles.py`). Add a regression case first. Never loosen a protect or veto pattern to gain recall.

## Lessons log
