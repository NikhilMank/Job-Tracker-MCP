---
name: jobtracker-gmail-sync
description: Update job tracker statuses (rejected / interviewing / offer) from Gmail evidence safely. Use when asked to sort, sync or reconcile jobtracker.db with the Gmail inbox or the JobApplications labels, mark rejections from emails, or check which applications got interviews or offers. Enforces an evidence standard that prevents mass misclassification.
---

# Sync job tracker statuses from Gmail

> **Label names:** this text writes the default parent label `JobApplications`. If the user chose another name it is saved as `label_prefix` in
> `data/routine-preferences.md` (or set via `JOBTRACKER_LABEL_PREFIX`); use that name wherever `JobApplications` appears. The scripts here already do.

A previous keyword-based run marked 30 jobs "offer" from job-alert digests and bootcamp
marketing mail, and 9 as "interviewing" from plain application confirmations. This skill
exists to make that impossible. **Precision beats coverage: a wrongly rejected live application
is worse than an unmatched email. Leave ambiguous cases unchanged and list them.**

## Ground rules
1. **Skip jobs already `rejected`** — closed; never re-open or re-evaluate them.
2. **Evidence standard** (all required to change a status):
   - the email *body* names the company **and** the specific job title (or the company has a
     single job in the tracker and the sender/subject names it),
   - the email is not older than the application date (`Applied: M/D/YYYY` in `notes`),
   - the wording is genuinely a rejection / interview invite / offer — for rejections this means the sentence-level
     classifier in `gmail-file-rejections/scripts/rejection_classifier.py` returns `REJECTION` (one sentence states the
     decision; never a keyword like "leider"),
   - the email was not sent by the user.
3. **Never infer interviews or offers from keywords** ("Angebot", "Termin", "Invitation", "offer").
   Marketing, Glassdoor/LinkedIn/Indeed digests, bootcamps, calendars and "thank you for applying"
   mails contain these words. Application confirmations are *not* status changes.
4. **Back up `jobtracker.db` before any write** (the scripts do), and write notes recording the
   evidence (`Rejected per email DATE (gmail:ID) [body-verified]`).
5. Never print or store credentials that appear in email bodies (assessment logins, portal passwords).

## Where the truth lives in Gmail
- `JobApplications/Rejected` — emails the user has filed as rejections . Rejections
  usually go here once handled, so an email can be a rejection for a job that is *already*
  `rejected` ("explained-rejected" — no action).
- `JobApplications/Shortlisted` — interview threads (genuine interviews).
- `JobApplications/Accepted` — offers/contracts. `Applied/*` labels are older (2023).
- Many interview/offer threads are for jobs that are **not in the tracker** (initiative
  applications). Report them; don't invent rows.
- Most companies with real interviews end up rejected, so few jobs ever become `interviewing`/`offer`.

## Workflow
Scripts are in `scripts/` (run from the project root with `.venv/bin/python`; the Gmail
token is `.gmail-token.json` — if missing, use the `gmail-mcp-troubleshooting` skill).

1. **Snapshot**: `.venv/bin/python scripts/backup_db.py` (writes `backups/jobtracker-<date>.db`, deletes copies older than 30 days; never create ad-hoc `jobtracker.db.bak-*` files) and note status counts. Note: a second backup on the same day overwrites the first, so take the snapshot before the first write of the day.
2. **Fetch the rejections with bodies** (slow, run in background, resumable). Normally only the recent ones:
   `fetch_gmail_label.py --query 'label:jobapplications-rejected after:YYYY/MM/DD -in:trash' --out work/`
   (the whole label, `--label "JobApplications/Rejected"`, only for a first/full reconcile)
   Gmail's per-minute quota is the limit: never loop one request per message; batching,
   throttling and retry are built in. 2,500 mails ≈ 10–15 min. Wait with an `until grep -q DONE log`
   background loop, not `sleep`.
3. **Match**: `match_rejections.py --emails work/emails.json --bodies work/bodies.json --out work/decisions.json`
   Classes: `UPDATE*` (safe), `explained-rejected`, `skip-predates`, `review*`, `nomatch`.
4. **Dry run, check it yourself, apply**: `apply_decisions.py --emails … --decisions …` (add `--review-csv <scratchpad>/review.csv` for your own use).
   Check every `UPDATE` row (company ↔ job title ↔ email subject), then re-run with `--apply`. Generic titles ("AI Engineer") at
   companies with several jobs are the usual false positives. Then resolve the `review` rows that are real rejections by reading the
   email next to the candidate rows (see "Settling ambiguity yourself").
5. **Interviews/offers** (manual, small): list `Shortlisted`/`Accepted` messages
   (`fetch_gmail_label.py --label … --no-bodies`), plus
   `--query 'after:YYYY/MM/DD -in:sent -label:JobApplications-Rejected (Einladung OR Gespräch OR interview OR assessment OR Vertrag OR "job offer")'`.
   Read the *bodies* of candidates. Mark `interviewing` only for a real invitation/test/call
   (screening call, aptitude test, interview link) tied to a specific job whose date is ≥ the
   application date and which is still `applied`. Mark `offer` only for an actual offer/contract.
6. **Report briefly**: counts before/after, what changed and why (company - role - email date), interview/offer threads for jobs
   not in the tracker, and anything genuinely unresolvable in one line. Do not hand the user a review list.

## Closing out `interviewing`
`interviewing` is temporary. When the user says they are not interviewing (or after a sync), settle each such job from Gmail:
a later rejection mail → `rejected`; the recruiter thread filed under `JobApplications/Rejected` → `rejected`; no outcome mail
(user's own follow-ups unanswered, silence for months) → `applied` + tag `no-answer` (the CSV's "No answer" mapping) with a note saying
what the last contact was. Keep the old "Interview stage: …" note. Never invent an outcome; never set `offer` without a real offer mail.

## Settling ambiguity yourself (the user does not want to verify anything)
The user has said they do not want to check or maintain tracker data: resolve ambiguity from Gmail evidence, do not hand back lists.
`match_rejections.py` already settles these by itself: **duplicate rows of the same role count as one application** (all rows get
the outcome), **job/ad numbers** quoted in the email (`1085/2026`, `E362/B`, `JR3800`) are matched against the job's url/description,
**acronyms** in company names (`(EMBL)`), junk keys (the greeting "Hallo" matched "Hallo Welt GmbH"), and the application date falls
back to the date the job was added (`scraped_at`) when there is no `Applied:` line, so an old 2025 rejection can never close a job
added in 2026. For what is left, read the email next to the candidate rows and decide (sender domain, role title, reference number,
the contact person noted in the job's `notes`). **Never auto-resolve on company name alone when the name is a generic word**
("Talent Tree", "Profile Software", "The Automation Group" produced wrong "only job at company" matches). Most remaining
"review" rows are not rejections of a tracked job at all (user replies, interview threads, "welcome" mails, jobs never in the tracker).

## Known pitfalls
- Jobs added later with `add_job` / `add_job_from_text` carry no `csv-import` tag and no `Applied:` note line: `match_rejections.py` now considers
  **all** jobs by default (`--tag` is optional). Run the sync on the recent Rejected label only (`label:jobapplications-rejected
  after:YYYY/MM/DD`), not the whole label. A company-only match whose job title differs from the email's role  is settled by reading further evidence (the
  job's `url`, the contact person in `notes`, whether it is the only application there).
- Sender names often differ from the tracker company (an abbreviation vs the full name) → that is
  why title evidence in the *body* matters; matching on sender/subject alone misses these.
- Tracker "company" values can be junk ("nicht erwähnt" = "not mentioned");
  `BAD_KEYS` in `match_rejections.py` blocks the known ones — add more when you meet them.
- Companies re-post the same job; identical titles at one company are **one candidacy**: the matcher gives all duplicate rows the
  outcome. Different titles at one company stay separate.
- Recruiter mass-mail and "Wir haben Ihre Bewerbung erhalten" lack rejection wording → never `UPDATE`.
- Quota errors (`Units per minute per user`) are transient; wait and resume, don't restart from scratch.
- `update_job` over MCP is one call per job; for bulk changes write to SQLite directly (with backup).
- Statuses allowed by the tool: new, applied, interviewing, offer, rejected, archived.

## Improving this skill
After each run, record new false positives/negatives in *Known pitfalls* and tune `match_rejections.py`
(thresholds, `BAD_KEYS`) and — for wording — `rejection_classifier.py` (run its `test_classifier.py` afterwards).
Helper scripts you write go in `scripts/`, never the project root.
