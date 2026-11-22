---
name: weekly-review
description: Produce a weekly job-search report from the tracker - how many applications, replies, interviews, rejections and offers, what is stale, and 3-5 concrete next actions. Use when the user says "weekly review", "how is my job search going", "job search stats", "what should I do this week", or on any request for a progress summary.
---

# Weekly review

Read-only. Turns the tracker into a funnel report and a short action list. Market- and field-agnostic.

## Prerequisites
- `jobtracker` MCP connected (`get_stats`, `list_jobs`, `get_job`).
- `data/profile.md` is optional; if present, use its **Weekly goals** to compare against.

## Steps
1. `get_stats` for totals, `by_status`, and the `recent_count` (jobs added in the last 7 days).
2. `list_jobs` per status (`applied`, `interviewing`, `offer`, `rejected`, `new`), paging as needed. **`list_jobs`
   returns only id, title, company, location, status, tags and `scraped_at` (date added): no notes.** Applied
   dates and evidence live in `notes` (e.g. `Applied: M/D/YYYY`), so call `get_job` for each `applied` and
   `interviewing` job (cap at 50, oldest first, and say if you capped). If a job has no applied date, say it is
   undated and use `scraped_at` only as 'added on', never as the applied date.
3. Compute, stating the period explicitly (last 7 days, plus the all-time funnel):
   - applied this week vs. goal; `new` backlog size
   - funnel: applied -> interviewing -> offer, and rejected share. **Report counts first; show a percentage
     only when the denominator is >= 10**, otherwise say the sample is too small to read.
   - stale applications: `applied` for >= 14 days whose notes show no later event than the `Applied:` date
     (the tracker has no updated-at field, so notes are the only evidence; oldest first, top 10)
   - open interviews and offers that need an action
4. Output, in this order and short:
   - **Snapshot** (table of counts).
   - **Wins** (interviews, offers, progress against goals).
   - **Stuck** (stale applications, undescribed jobs, backlog).
   - **Next actions**: 3-5 specific items, each naming a job or a skill to run (`job-fit-scorer` for the
     backlog, a follow-up on a named stale application, interview prep for a named interview).
5. Write nothing. If the user wants the report saved, put it in `data/weekly-YYYY-MM-DD.md` (git-ignored).

## Rules
- Do not invent dates, outcomes, or response rates the data does not contain.
- Keep the tone factual and encouraging; a rejection count is information, not a verdict on the user.
