---
name: job-fit-scorer
description: Score jobs in the tracker against the user's profile and recommend apply / maybe / skip. Use when the user says "which jobs should I apply to", "rank my new jobs", "score my saved jobs", "triage my backlog", or after adding new jobs. Reads data/profile.md and jobs via the jobtracker MCP; writes tags and notes only after approval.
---

# Job fit scorer

Ranks jobs with `status='new'` (or ones the user names) by how well they match the profile, and explains why.
Works for any field and market: the criteria come from the profile, not from this file.

## Prerequisites
- `jobtracker` MCP connected (`list_jobs`, `get_job`, `update_job`).
- `data/profile.md` exists. If not, run the `profile-setup` skill first. Sections marked `(not set)` are
  skipped and must be mentioned in the report so the user knows the score is partial.

## Steps
1. Read `data/profile.md`.
2. `list_jobs(status="new", limit=50)`; page with `offset` for more. If the user named jobs, use `get_job`.
3. For each job, `get_job` to read the full description. **If the description is missing or too short to judge,
   do not score it** (rule of thumb: under about 250 characters, or no responsibilities or requirements you
   can match): list it under "Needs a description" (the tracker treats a missing JD as a problem to
   fix with `update_job(description=...)` once the real text is found).
4. Score each job 0-100 using these weighted criteria, only counting criteria the profile defines:
   | Criterion | Weight | Judge from |
   |---|---|---|
   | Role / seniority match | 30 | title, responsibilities vs. Targets |
   | Skills overlap | 30 | requirements vs. Core/Working skills |
   | Location, work mode, language, permit | 20 | posting vs. Location & work mode |
   | Compensation | 10 | stated salary vs. Compensation (neutral 5/10 if the posting gives none) |
   | Industry / company fit and nice-to-haves | 10 | posting vs. Targets, Nice-to-haves |
   **Rescaling:** drop a criterion only when its profile section is entirely `(not set)`; judge a partly-set
   section (e.g. home city but no work-mode preference) on what is defined. Divide the points earned by the
   points available and multiply by 100; round to a whole number. If the posting states a salary but the profile
   has no pay targets, drop the compensation criterion. Within a criterion, use bands: full weight = clear match,
   about half = partial, about a quarter = weak, zero = contradicts. The profile's Experience summary is a valid
   source for skills and seniority; mark an `[inferred]` seniority in the report.
5. **Deal-breakers override the score**: any hit on the profile's Deal-breakers (or a hard permit/language
   requirement the user is known not to meet) caps the verdict at `skip`, and the reason must quote the
   posting. If the profile's permit or language is `(not set)`, do not cap: report the requirement as
   "unverified" in the biggest-gap column and ask the user.
6. Verdict: `apply` (>= 70), `maybe` (45-69), `skip` (< 45 or deal-breaker).
7. Report a table sorted by score: job id, title, company, score, verdict, a one-line reason, and the biggest
   gap (write "none material" if there is none). Break ties by role-match points. Base every statement on the posting text and the profile; never assume facts about the company that
   are not in the data.
8. **Ask before writing.** On approval, for each job call `update_job(id, tags=..., notes=...)`. `tags` and
   `notes` are *replaced*, so first read the existing values with `get_job` and merge (`tags` come back as a
   JSON string like `["ai"]`, or null; parse it): keep the old tags, add one of
   `fit:apply`, `fit:maybe`, `fit:skip` (remove any previous `fit:*` tag), and append a note line
   `Fit YYYY-MM-DD: 78/100 - reason`. Do **not** change `status`; skipping a job is the user's call (offer
   `archived` separately).

## Honesty rules
- The score is a decision aid, not a prediction of the hiring outcome. Say so once in the report.
- Never recommend rejecting or deprioritising someone based on age, gender, nationality, family status or
  any protected characteristic; the profile contains none of these and the posting text must not be read
  for them.
