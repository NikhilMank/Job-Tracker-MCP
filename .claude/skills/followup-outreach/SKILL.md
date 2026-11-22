---
name: followup-outreach
description: Find applications with no reply after a set number of days and draft polite follow-ups, plus draft networking/referral messages. Use when the user says "follow up on my applications", "who haven't I heard back from", "draft a LinkedIn message", "ask for a referral", or "thank-you email after an interview".
---

# Follow-up and outreach

Finds stale applications and drafts messages. **Drafts only**: nothing is sent, posted, or messaged unless
the user explicitly says to send that specific message.

## Prerequisites
- `jobtracker` MCP (`list_jobs`, `get_job`, `update_job`). Gmail MCP is optional (read replies, create
  drafts if available; `send_email` only on explicit instruction per message).

## Rules
- Respect the recipient: short, specific, one clear ask, no pressure, no guilt.
- Do not send repeated follow-ups: at most one follow-up per application after the initial wait and one
  more after a further wait, then suggest closing it out (`archived`) with the user's approval.
- Use only recipient names and contact details the user or the posting provides. Do not guess email
  addresses or scrape personal data. Do not invent shared connections.
- Keep personal data out of the notes you save: record "follow-up drafted YYYY-MM-DD", not message text
  with third-party names.

## Steps
1. Ask for the waiting period (default: first follow-up 10 days after applying, second follow-up 14 days after the first) and the channel
   (email or LinkedIn message).
2. `list_jobs(status="applied")` (page as needed). `list_jobs` does not return notes, so call `get_job` per
   job: application dates live in `notes` (e.g. `Applied: M/D/YYYY`) together with any `Followup ...` notes. Skip jobs with no applied date (list them as
   undated). If Gmail is connected, check for any reply before drafting; do not nag if one exists.
3. Show a table: job id, company, title, days since applied, follow-ups so far, suggested action
   (`follow up`, `second follow-up`, `close out`, `undated`).
4. For each job the user selects, `get_job` and draft a message of 3-5 sentences: reference the role and
   application date, restate one concrete reason for fit, ask about timeline/next steps, thank them.
5. Other drafts on request:
   - **Referral/networking ask**: who they are, why this company/role, a specific small ask, easy
     opt-out.
   - **Post-interview thank-you** within 24 hours: one specific moment from the conversation (supplied
     by the user), reaffirmed interest.
6. On approval, merge a note into the job's `notes` via `update_job` (it replaces; read existing notes
   first): `Followup 1 drafted YYYY-MM-DD`. Do not change `status`.
