---
name: gmail-job-inbox-triage
description: End-to-end maintenance of the job-related Gmail inbox - delete platform job suggestions (LinkedIn/Stepstone/Glassdoor/XING/jobvector/Instaffo), read company job-agent letters and report the AI roles in them (trashing them only after the user says so), and triage everything else into needs-you, rejections, application confirmations, Easy Apply receipts and doubtful mail, filing the clear ones; only newer mail is read after the first run. Use when the user says "sort/clean my job emails or inbox", "I applied and got replies", "delete job suggestions", or wants new rejections and confirmations handled together. Orchestrates gmail-file-rejections and gmail-file-applications; precision first.
---

# Job inbox maintenance (suggestions + company letters + triage)

One routine for the whole job inbox. The single-purpose skills still work on their own: `gmail-file-applications` (receipts),
`gmail-file-rejections` (rejections). All of them share one principle.

## Principle: precision over recall
A false positive hides a real email (interview invitation, offer, a request with a deadline); a false negative is free.
- Never move/trash anything that is not classified with high confidence **or** read by you and found clear (the user wants you to
  settle doubtful mail yourself instead of verifying it - but never guess).
- Surface mail that needs the user **first**; never bury it in a count.
- Every move/trash writes an undo log; "delete" always means **Trash** (never permanent).
- Platforms mix suggestions with mail that matters (LinkedIn `jobs-noreply` sends job suggestions AND your application
  receipts/"viewed"/"application updates"). Decide by **sender + subject**, never by sender alone.

## When it runs
**Only when the user asks** ("clean my job mails"). No schedule, no background automation. Platform alerts and
company letters keep arriving, so a cleanup only removes what exists at that moment: say so in the report, and mention how many
new ones arrived since the last run (`mail_state.py show` gives the last-run time).

## The routine (in this order)
Prerequisites: `.gmail-token.json` with `gmail.modify` (`gmail-mcp-troubleshooting`); run from the project root with
`.venv/bin/python`; put downloads in the session scratchpad, helper scripts in `scripts/`. Downloads are slow and resumable:
run them in the background and wait with an `until grep -q DONE <log>` loop, not `sleep`.

**0. Saved run time.** `scripts/mail_state.py show`. After the first full sweep every task reads only mail **newer than its
last completed run** plus its *pending ids* (mails deliberately left behind), so runs stay cheap. See "Saved run time" below.

**A. Job-suggestion cleanup** (when you add or change a rule, run it once with `--since all`: the saved run time otherwise hides older mail that the new rule would catch) - `scripts/clean_job_suggestions.py --out <scratchpad>/sugg [--since all] ` (dry run), look at the
"would trash" counts and the "kept" list, then re-run with `--apply`. Trashes job *suggestions* from LinkedIn (job alerts,
"looking for a new job?", "X is hiring", "apply now to…"), Stepstone, Glassdoor, XING, jobvector, Instaffo, Indeed alerts.
Protected and only listed: application receipts/updates ("your application was sent/viewed", "Bewerbung über Indeed",
"in der engeren Auswahl", "application updates"), recruiter messages, connection requests, billing/security mail. Other platform
mail that is not a suggestion (LinkedIn group digests, "your posts got N impressions", XING "Kennst Du …?", employer promos) is
listed, not trashed - ask the user once whether to include those categories. Undo: `--undo data/trashed_emails_log/<log>.json`.
Watch for shortlisted/positive platform mail in the "kept" list (e.g. Stepstone "Ihre Bewerbung … ist in der engeren Auswahl")
and mention it.

**B. Company job letters** - `scripts/scan_company_jobletters.py --out <scratchpad>/cjl [--since all]` reads the
SuccessFactors/jobs2web job-agent letters (large employers' careers-site mailers). The job list is one
run-on string, so the automatic extraction glues neighbouring titles: **read the recent letters yourself and report real role
titles** (AI/ML/KI/LLM/GenAI/Data Science/Computer Vision; list Data Engineer-type roles as "related"; mark internships,
working-student roles and study programmes as such). Ignore the letter preamble: it repeats the user's own saved search
("Data Scientist, Luxembourg"). Letters carry no job links in the extracted text - tell the user to search the company's career
site. **Report the AI roles first, then WAIT. Trash the letters only when the user says so, every time** (the user's rule:
"you trash them after I say"; an earlier one-off yes does not carry over). Only then re-run with `--trash` (undo log
`data/trashed_emails_log/*-companyletters.json`). If one sender keeps returning, mention its unsubscribe link.

**C. Inbox triage** - `scripts/triage_inbox.py --out <scratchpad>/triage` (read-only) classifies recent inbox mail:
| Bucket | Meaning | Action |
|---|---|---|
| `SHORTLISTED` | **positive reply**: interview invitation, "shortlisted / next stage", offer | **Standing rule:** (1) star it, (2) add the label `JobApplications/Shortlisted`, (3) set the tracker job to `interviewing` (`offer` for an offer) when the mail names company **and** title. **The mail stays in the inbox** (do not move it, do not remove Inbox). Use `scripts/mark_shortlisted.py --ids shortlisted.json --apply`. If the mail asks the user to act (book/confirm an appointment, reply, take a test), also add `JobApplications/NeedsAttention`. Report first. |
| `STALE_PROFILE` | "we will delete your profile/data soon because of inactivity - log in to keep it" (imminent deletion + call to log in; a plain data-retention sentence in a receipt/rejection does NOT count) | **Standing rule: trash** with `scripts/trash_emails.py --ids stale_profile.json --apply` (dry run first; undo log in `data/trashed_emails_log/`) |
| `NEEDS_YOU` | about the user's application AND an explicit request (personality test, **automated online assessment / coding challenge such as ELIGO/Harver/Codility, not a positive reply but still an action for the user**, certificate/documents, e-mail confirmation, portal password setup), a real (non-conditional) interview invitation, or an offer/contract | **Report first** with task + deadline. Gets `JobApplications/NeedsAttention`, stays in the inbox, never moved. |
| `REJECTION` | one decision sentence, no invitation/request in the message (`rejection_classifier`, 0 false positives on 1,600 non-rejection mails) | **file** → `JobApplications/Rejected` (standing instruction), then report each with its deciding sentence |
| `CONFIRM` | plain acknowledgement, no risk wording (`confirmation_classifier`) | file → `JobApplications` |
| `CONFIRM_EASY` | LinkedIn Easy Apply receipt (sender linkedin.com only) | file → `JobApplications` + `JobApplications/EasyApply` |
| `DOUBTFUL` | acknowledgement/rejection wording **and** risk wording, an invitation, a request, a footer or a long text | **read each one** (the triggering context is easy to print); file those you find to be plain receipts or plain rejections, leave the rest |
| `UNCLASSIFIED` | job-related mail from a company/ATS that **no rule recognised** (new wording, odd subject, status update like a "status update" mail) | **read each one**, settle it like `DOUBTFUL`. These ids stay pending until filed.  If you file/decide one by hand and the pattern is generic, add a case to `test_triage.py` / `test_confirmation.py` / `test_classifier.py` and fix the pattern |
The rules live in `scripts/triage_rules.py` (`triage_one`), tested by `scripts/test_triage.py` (run it after every change; real missed mails are the cases).
It writes `plan.json` and candidate lists `rejected.json`, `confirm.json`, `confirm_easy.json`. Typical harmless doubtful triggers:
"Telefon" in a signature, "kurzfristig", "don't forget", "etwas Zeit benötigen", Stepstone's "apply to similar jobs" footer.

**D. Report to the user, in this order:** (1) `NEEDS_YOU` with the reason, (2) shortlisted/positive mail found anywhere,
(3) AI roles from company letters, (4) rejections filed, each with its deciding sentence, (5) receipts filed (counts),
(6) doubtful mail grouped as "plain receipts that tripped a keyword / rejections / needs you", (7) what was trashed (+ undo logs) and, if company letters are still waiting, ask whether to trash them,
(8) tracker changes (jobs marked rejected, `interviewing` closed out), (9) the few real decisions left for the user (platform non-suggestion
categories, company letters waiting for "trash them").

**E. File what is clear** with `gmail-file-rejections/scripts/move_emails.py` (dry run, then `--apply`; it verifies and writes an
undo log in `data/moved_emails_log/`; use **full ids**):
- rejections: `--ids rejected.json --to JobApplications/Rejected` (removes Inbox + parent label)
- receipts: `--ids confirm.json --to JobApplications`
- Easy Apply: `--ids confirm_easy.json --to JobApplications --also-add JobApplications/EasyApply`
High-confidence `REJECTION` and `CONFIRM*` are filed as soon as the user has asked for the inbox to be sorted - do NOT leave them
waiting for another yes (that delay was a mistake: the user asked why rejections were still unfiled). From `DOUBTFUL`, file the
ones you have read and found to be plain receipts or plain rejections - the user wants you to settle these yourself, not to verify
them. Mail that needs the user stays in the inbox. Report what was filed, with the deciding sentences and the undo-log path. `EasyApply` is **LinkedIn only** (569/569 existing messages); Indeed/Stepstone receipts get
the parent label only.

**F. Commit the run time** (only now, after the report): `triage_inbox.py --out … --no-fetch --commit` (stores the unresolved
ids = needs-you + doubtful + rejection candidates). Suggestion cleanup and company letters commit themselves on `--apply` /
`--trash` (or `--commit`). Then **update the tracker yourself** (not optional - the user does not want to maintain it): `jobtracker-gmail-sync` on the rejections filed in
this run (backup first, company **and** title evidence, apply the clear matches) and close out `interviewing` jobs whose outcome is known.

## Saved run time (only read new mail)
`scripts/mail_state.py` keeps `data/job_mail_state.json`: per task the START time of the last completed run + `pending_ids`.
- `--since auto` (default) = mail newer than that run (minus a 1 h overlap) **plus the pending ids**. Without the pending ids a time
  filter would silently drop mail that was deliberately left (needs-you, doubtful mail still unresolved).
- State is written only by an explicit commit **after** the report; a failed or unreported run must not advance it.
- The stored time is when the mailbox was *read* (download start), never the later apply step. With `--no-fetch` the scripts use the
  download file's mtime minus 2 h. (A first version stored the apply time and would have skipped mail that arrived in between.)
- `--since all` = whole mailbox, ignores state (first sweep); `--since N` = last N days; `mail_state.py reset <task>` clears a task.
- Tasks: `job_inbox_triage`, `job_suggestions`, `company_jobletters`.

## Label conventions
Label conventions: Rejected → `JobApplications/Rejected`; receipts → `JobApplications` only;
Easy Apply → parent + `/EasyApply`; there is **no** `JobApplications/Applied`.

## Improving
When something is misbucketed, fix the cause where it lives (add a regression case first): wording →
`gmail-file-rejections/scripts/rejection_classifier.py` (+ `test_classifier.py`) or
`gmail-file-applications/scripts/confirmation_classifier.py` (+ `test_confirmation.py`); NEEDS_YOU rules (`STRONG_ACTION`, `OFFER`,
`NOISE`) in `triage_inbox.py`; suggestion rules/protect list (`RULES`, `PROTECT`) in `clean_job_suggestions.py`. Never loosen a
veto or protect pattern to gain recall. Helper scripts go in `scripts/`, never the project root.


## Gotchas
- **Never run several Gmail MCP calls in parallel** (`search_emails` / `get_email`): they time out or hit SSL errors, and one `get_email` returned a *different* message than the id requested. Check that the returned subject matches what you asked for. For anything bulk use `jobtracker-gmail-sync/scripts/fetch_gmail_label.py --query ...` (reads many mails reliably; `emails.json` fields are `id, subject, frm, date, labels, snippet`).
- When the user names a sender you "missed", first fetch it (`--query 'from:<sender> in:anywhere'`) and replay it through `triage_rules.triage_one`; the bucket (or None) shows which rule failed. Then fix the rule and add the case to the tests.
- The saved run time hides older mail. After changing any rule, sweep with `--since 14` (triage) or `--since all` (suggestion cleanup), as a verification pass at the end of every routine.

## Gotchas
- **Silent drops.** `triage_one` returns `None` for mail with no job wording, so a company mail that matched no rule was invisible. Fixed with: `CONSENT_RETENTION` (consent / "we still store your data" mails -> `STALE_PROFILE`, trashed), `RESCHEDULE` (interview time change / cancellation -> `NEEDS_YOU`, also update `data/shortlisted.md`), `ACCOUNT_CREATED` and `APPLICATION_SURVEY` (-> `CONFIRM`, filed), talent newsletters added to `NOISE` and to the `talent newsletters` rule in `clean_job_suggestions.py`, and a final safety net: a career/recruiting sender with job wording that no rule matched is `UNCLASSIFIED`. Regression cases are in `test_triage.py`; run it after every rule change.
- **Alert rules were too narrow:** Instaffo "Könnte gut zu dir passen / Neuer Job / wartet auf dich", Workwise "Jobs passen", Stepstone "Your progress ... new job matches" were kept as "not a job suggestion". Glassdoor mails were protected by the word `security` in the job title; `PROTECT` now only matches security alerts/codes.
- **Mail can be missing from the triage download entirely** (the Vendor "Einladung zum Online Assessment" of 5 Nov and the Globex confirmation were not in `bodies.json`). The time filter and pending ids are not a guarantee. So the routine ends with an **inbox sweep** (see `daily-job-routine` step 5d): list the whole inbox from the last 21 days independent of the saved run time and account for every job-related mail.
- Never decide "nothing left" from the triage output alone; the verification pass reads the same download.
