---
name: cover-letter-writer
description: Draft a tailored cover letter or short application message for a tracked job from the user's profile and CV. Use when the user says "write a cover letter for this job", "draft an application email", "motivation letter", or needs a short pitch for an application form.
---

# Cover letter writer

Writes a concise, specific cover letter in the user's voice. Works for any field, country and language.

## Prerequisites
- `jobtracker` MCP (`get_job`, `search_jobs`, `update_job`).
- `data/cv.md` and `data/profile.md` (run `profile-setup` if missing). Ask for 1-2 sentences on *why this
  company/role* if neither the posting nor the profile gives a real reason; do not fabricate enthusiasm.

## Rules
- Use only facts from the CV, the profile, the posting, and what the user tells you. Never invent
  achievements, numbers, relationships ("I met your CEO"), or knowledge about the company beyond the
  posting. If company detail is needed (mission, product), take it from the posting or ask the user.
- Do not mention protected or irrelevant personal details (age, marital status, health, religion, photo)
  even if the local convention includes them; the user can add them.
- Never send anything. This skill drafts; sending an email needs a separate explicit instruction.

## Steps
1. Identify the job and `get_job` for the full description (stop if the description is missing/short).
2. Ask the user for: language, tone (formal / warm / concise), length limit, and the name of the hiring
   contact if known. Default to the posting's language, 250-350 words, three paragraphs.
3. Structure:
   - **Opening**: the role, and one specific reason it fits (from the posting).
   - **Evidence**: 2-3 achievements from the CV mapped to the posting's top requirements, each with its
     real result.
   - **Close**: motivation, availability/notice period only if the user gave it, a polite call to action.
4. Provide the full letter plus a **short variant** (about 80 words) for application forms or an email body.
5. List any claim you want the user to double-check, and any requirement you could not address honestly.
6. Save only if asked (`data/letter-<company>-<title>.md`, git-ignored). On approval, merge a note into the
   job's `notes` via `update_job` (it replaces; read old notes first). Never change `status`.
