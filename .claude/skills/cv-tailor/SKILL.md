---
name: cv-tailor
description: Tailor the user's CV to a specific tracked job - compare the job description with their CV, list matched and missing requirements, and rewrite bullets to fit using only true experience. Use when the user says "tailor my CV for this job", "adapt my resume", "what is missing from my CV for job X", or before applying to a saved job.
---

# CV tailor

Produces a job-specific CV draft and a gap report. Works for any field, language and CV format.

## Prerequisites
- `jobtracker` MCP (`get_job`, `search_jobs`, `update_job`).
- The user's master CV in `data/cv.md` (plain text/Markdown). If missing, ask the user to paste it or give
  a file path, and offer to save it to `data/cv.md` (git-ignored). Read `data/profile.md` if present.

## Hard rules (truthfulness)
- **Never invent or inflate** experience, employers, titles, dates, degrees, certifications, metrics, or
  tools. Only reword, reorder, emphasise, or cut what the CV already says.
- If a requirement is not supported by the CV, list it as a **gap**. Never paper over it. Suggest honest
  options: a related skill the user has, a quick way to learn it, or ask the user whether they have
  experience the CV omits (add only if they confirm, in their words).
- Keywords from the job description may be mirrored only where they truthfully describe the user's work.
- Keep the user's contact details and personal data out of anything you save to the tracker or send to
  external services.

## Steps
1. Identify the job (id, or `search_jobs` by company/title) and `get_job` for the full description. If the
   description is missing or too short, stop and say so: fix it first (`update_job(description=...)`).
2. Read `data/cv.md`. Extract from the job: must-have requirements, nice-to-haves, key responsibilities,
   and the vocabulary the posting uses.
3. **Match table**: each requirement -> `strong` / `partial` / `missing`, with the CV line that is the
   evidence (quote it) or "no evidence".
4. **Tailored CV draft**, same structure and language as the master CV (match the posting's language only
   if the user asks):
   - summary rewritten for this role (2-4 lines, no unverifiable claims)
   - experience bullets reordered and reworded so relevant evidence comes first; each bullet keeps its
     original facts and numbers
   - skills section reordered to lead with matches
   - drop or shorten irrelevant items; keep it to the length the user's market expects (ask if unsure)
5. **Change log**: list every edit as `before -> after` so the user can verify nothing was invented.
6. Save the draft only if asked, to `data/cv-<company>-<title>.md` (git-ignored). On approval, append a
   note to the job via `update_job(notes=...)`: read the old notes and merge (it replaces), e.g.
   `CV tailored YYYY-MM-DD: data/cv-<company>-<title>.md`. Do not change `status`.

## Notes
- ATS-friendliness: plain headings, no tables/images in the text version; mention this once.
- Employment-law or visa questions raised by a posting are outside this skill; flag them for a qualified
  professional.
