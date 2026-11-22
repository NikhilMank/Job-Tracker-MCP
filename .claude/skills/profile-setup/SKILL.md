---
name: profile-setup
description: Create or update the user's private job-search profile (data/profile.md) by interviewing them. Use when the user is new, says "set up my profile", "update my preferences", "change my target roles/salary/location", or when another skill (job-fit-scorer, cv-tailor, interview-prep) needs a profile and data/profile.md does not exist.
---

# Profile setup

Other skills (`job-fit-scorer`, future CV/cover-letter/interview skills) judge jobs against the user's
goals. This skill creates that source of truth. It is written for **any user, any country, any field**:
never assume a market, language, currency, or job board.

## Rules
- The profile is personal data. It lives in `data/profile.md` (git-ignored via `data/*`). Never write it
  anywhere that is committed, never print it into commit messages, issues, or external requests.
- Do not ask for or record special-category data (health, religion, ethnicity, union membership, etc.).
  If the user volunteers it, leave it out of the file. Visa/work-permit status is allowed only as the
  practical yes/no plus what the employer must provide.
- Ask only what is missing. Keep it conversational: 2-4 questions at a time, in the order of the template
  sections. Offer sensible examples but never fill an answer in for the user.
- Do not invent skills or experience. Everything in the file comes from the user (or from a CV they
  point you to and confirm).

## Steps
1. If `data/profile.md` exists, read it, show a 5-line summary, and ask what to change. Otherwise start from
   `.claude/skills/profile-setup/profile.template.md`.
2. If the user already has a CV/resume (file path or pasted text), switch to the `profile-from-resume`
   skill: it extracts the facts first and then asks only about the gaps. Otherwise continue below.
3. Interview for the empty sections. Mark anything the user skips as `(not set)` so downstream skills know to
   ask or fall back to neutral scoring.
4. Write `data/profile.md`, then print the final profile back and confirm.
5. Tell the user which skills can now run, and that they can re-run this skill any time.

## Output format
Keep the template's headings exactly: other skills parse by heading name. Bullet values are free text.
