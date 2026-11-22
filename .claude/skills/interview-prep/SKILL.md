---
name: interview-prep
description: Build an interview preparation pack for a tracked job - likely questions, STAR stories drawn from the user's real experience, questions to ask the interviewer, and a mock interview on request. Use when the user says "prepare me for my interview", "mock interview", "what will they ask me", or when a job is set to interviewing.
---

# Interview prep

Turns a job description plus the user's real experience into a practice plan. Any field and country.

## Prerequisites
- `jobtracker` MCP (`get_job`, `search_jobs`, `list_jobs`, `update_job`).
- `data/cv.md` and `data/profile.md` (run `profile-setup` if missing).
- Optional: interview notes the user keeps (e.g. `data/shortlisted.md`); read them if they exist.

## Rules
- Stories must come from the user's actual experience. If there is no matching story for a likely
  question, say so and help the user find one from what they tell you; never write a fictional example.
- Company facts come only from the posting, notes, or what the user pastes. If current company
  information (news, product, culture) would help, say so and offer to use a web search only if the user
  asks, and label it as externally sourced.
- Salary/negotiation advice is general guidance only; legal or employment-law questions need review by a
  qualified professional.

## Steps
1. Identify the job and `get_job`; read the CV and profile. Ask: interview type (recruiter screen,
   technical, case, panel, behavioural), date, interviewers' roles, and time available to prepare.
2. **Pack** (keep it scannable):
   - **What they are testing**: the 4-6 competencies the posting implies.
   - **Likely questions** per competency (role-specific, behavioural, motivation, and the hard ones:
     gaps, why leaving, salary expectations).
   - **STAR story bank**: for each competency a story from the CV: Situation, Task, Action, Result (with
     the real numbers), plus a one-line "so what". Flag competencies with no story yet.
   - **Gaps and honest answers**: for each `missing`/`partial` requirement, a truthful framing and a plan.
   - **Questions to ask them**: 5-8 thoughtful ones tied to the role, team, and success measures.
   - **Logistics checklist**: documents, timezone/tools, follow-up thank-you message.
3. **Mock interview mode** on request: ask one question at a time, wait for the user's answer, then give
   feedback (structure, specificity, evidence, length) and a stronger version using only their facts. Keep
   a running list of weak answers to revisit.
4. On approval, record a brief note in the job (`update_job(notes=...)`, merging old notes since it
   replaces): date prepared, interview type, top 3 stories. Set `status="interviewing"` only if the user
   says an interview is actually scheduled.
