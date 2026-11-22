---
name: profile-from-resume
description: Build the user's job-search profile (data/profile.md) from an existing resume/CV, then ask only the follow-up questions needed to fill what a resume cannot tell (target roles, pay, location, deal-breakers). Use when the user says "build my profile from my resume", "I already have a CV", "import my resume", or shares a resume file or text while setting up.
---

# Profile from resume

Fast path to `data/profile.md`: extract what the resume states, let the user confirm it, then ask only about
the gaps. Works for any field, country and language. Output format is the same as `profile-setup`, so every
other skill (`job-fit-scorer`, `cv-tailor`, `interview-prep`, ...) works unchanged.

## Privacy rules
- A resume is full of personal data. Copy into the profile **only what the job-search skills need**:
  skills, roles, seniority, industries, languages, a short experience summary. **Do not copy** name, address,
  phone, email, date of birth, photo, nationality, marital status, or references into `data/profile.md`.
- Never record or infer special-category data (health, religion, ethnicity, union membership, etc.), even if the
  resume mentions it (volunteering for a religious or political group, a disability note, ...). Leave it out.
- Do not infer age, gender, or family status from dates or names, and do not use them anywhere.
- Everything stays local: `data/profile.md` and `data/cv.md` are git-ignored. Never paste resume content into
  external services, search queries, commit messages, or tracker notes.
- Save the full resume text to `data/cv.md` only if the user agrees (other skills use it). Ask once.

## Steps
1. **Get the resume.** Ask for a file path or pasted text.
   - `.md`, `.txt`: read directly. PDF: use the Read tool (`pages` for long files); it needs poppler (`pdftoppm`), so if it errors,
     extract the text another way (`pdftotext`, or on macOS a few lines of Swift using `PDFKit`'s
     `PDFDocument.string`) or ask for pasted text. `.docx`: extract the text with
     `python3 -I` and the standard library (`zipfile`, turn `</w:p>` into newlines, strip tags, `html.unescape` the
     text of `word/document.xml`; tested, only works for text-based files, not tables-as-images), or ask
     for a PDF/paste if that fails. Scanned image PDFs: say text could not be read and ask for pasted text.
   - If `data/profile.md` already exists, read it and treat this as a merge, not an overwrite.
2. **Extract**, strictly from the text:
   - roles held and a seniority estimate (state the evidence, e.g. "6 years in X")
   - skills grouped as **Core** (used repeatedly / recently / in several roles), **Working** (mentioned
     once or older), **Learning/adjacent** (courses, side projects, certifications in progress)
   - industries and company types worked in
   - languages and stated levels
   - education and certifications relevant to the target field
   - a 3-6 line experience summary in neutral words (no invented achievements, keep real numbers)
3. **Show an extraction review** in a table: item, value, evidence (quote or section), confidence
   (`stated` / `inferred`). Ask the user to correct, remove, or add. Anything `inferred` must be confirmed
   before saving.
4. **Ask only about gaps.** A resume cannot tell you these, so ask them (2-4 questions at a time, skipping
   anything the user already answered):
   - target roles and seniority (current role may not be the goal), industries to prefer or avoid
   - location, remote/hybrid/onsite preference, work-permit needs, acceptable relocation
   - compensation: currency, pay period, minimum and target
   - deal-breakers and nice-to-haves
   - weekly goals (applications, networking messages)
   Also ask targeted refinement questions only where the resume leaves a real hole: employment gaps the user
   may want framed, a career change, skills implied but unproven, recent (last 2 years) work that looks thin.
   Do not ask about things unrelated to job fit.
5. **Write `data/profile.md`** using the headings of `.claude/skills/profile-setup/profile.template.md`
   exactly (other skills parse by heading). Unanswered items stay `(not set)`. Print the final profile and
   confirm it.
6. Offer `data/cv.md` (see privacy rules), then suggest next steps: `job-fit-scorer` on saved jobs, or
   `cv-tailor` for a specific one.

## Quality checks before saving
- Every skill and claim in the profile traces to the resume or to an answer the user gave.
- No contact details or special-category data are in the file.
- Core skills are not inflated: a one-line mention is `Working` at most.
