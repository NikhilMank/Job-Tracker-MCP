---
name: gmail-file-rejections
description: Find recent job-rejection emails in the Gmail inbox and file them into the JobApplications/Rejected label the way the user does (target label added, Inbox and parent label removed). Use when the user says they received new rejections, asks to move/sort/file rejection emails, or to clean the inbox of job rejections. A sentence-level classifier decides what is a rejection; never decide from a keyword. Pair with jobtracker-gmail-sync to update tracker statuses afterwards.
---

# File new rejection emails into `JobApplications/Rejected`

## Principle: precision over recall
**A false positive is dangerous, a false negative is fine.** Filing a non-rejection (an interview invite, an offer,
a request to act) out of the inbox can make the user miss it; a rejection that stays in the inbox costs nothing.
So whenever in doubt: leave it, and list it for the user. Concretely:
- Only verdict `REJECTION` (high confidence) is filed on its own; `CHECK` mail is never filed unless the user has read it
  and says so for that message.
- Filing rejections out of the inbox is the user's choice (`file_rejections` in `data/routine-preferences.md`, asked once by `daily-job-routine`; if it is not set, ask before filing anything). When it is `yes`, file the high-confidence ones **right away**, then show the list
  (company, subject, deciding sentence) and the undo log. Do not hold them back waiting for a second yes - that delay is
  what the user complained about ("why did you not file them yet?").
- Every move writes an undo log (`data/moved_emails_log/*.json`); `move_emails.py --undo <log>` restores the original
  labels exactly (tested). Tell the user the log path.
- Never send or trash anything. Never move more than was classified `REJECTION` or read and found to be a plain rejection.

## What counts as a rejection (the classifier's rule)
**A mail is a rejection only if one sentence of the sender's own, unquoted text states the decision against
the candidate.** A lone "leider" / "unfortunately" proves nothing. The templates come from the user's own
a large set of filed rejections, e.g.:
- DE: "…müssen wir dir leider mitteilen, dass wir deine Bewerbung nicht (weiter zu) berücksichtigen (können)",
  "nicht in die engere Auswahl", "haben uns für einen anderen/eine/n andere/n Bewerber/in entschieden",
  "Kandidaten, deren Profil noch besser zu den Anforderungen passt", "Stelle ist bereits besetzt/vergeben",
  "es hat dieses Mal leider nicht geklappt", "keine passende Position anbieten", "Absage", "… nicht weiterzuführen".
- EN: "we will not be moving forward with your application", "decided to move forward with other candidates",
  "we regret to inform you…", "could not shortlist", "we don't see a strong match", "position has been filled /
  vacancy has been closed", "we have otherwise occupied the position", "no longer being considered".
- NL/SV/NO/PL/FR/ES: "helaas… tegenkandidaten / besloten verder te gaan met…", "inte gått vidare", "ikke gå videre",
  "nie będziemy kontynuować…", "malheureusement … pas retenu", "lamentablemente…".

Looks like a rejection but is **not** (the classifier vetoes these; they were all real misfires):
- delay: "leider verzögert sich der Auswahlprozess" · scheduling: "der Termin passt leider nicht", "need to reschedule"
- action request: "Ohne diesen Schritt können wir deine Bewerbung leider nicht weiter bearbeiten" (personality test)
- conditional/hypothetical: "Falls/If we can't consider you…", "If you are not selected…", "Sobald wir eine Auswahl getroffen haben…"
- hedged: "Stelle möglicherweise schon besetzt" · mass-mail apology: "we can't respond to every candidate"
- boilerplate: GDPR "otherwise we will delete your data and will not be able to continue working with you"
- quoted/forwarded text, the user's own replies, "is the right fit" (positive), invitations that mention interviews.
Concessive "Auch wenn uns deine Unterlagen gut gefallen haben, können wir … leider nicht berücksichtigen" **is** a rejection.

Verdicts: `REJECTION` — a specific decision phrase in one sentence of the sender's own text near the top, the message
refers to the user's own application, and it contains **no interview invitation or request to act anywhere** ·
`UNCLEAR` — everything doubtful: generic "leider … nicht" wording without a decision phrase (this tier never counts
as a rejection by itself), decision wording only in quote/subject/conditional sentences, a rejection plus an invitation
in the same message, a decision deep in the text (boilerplate?), or no reference to the user's application ·
`NOT_REJECTION`. Several broad patterns were tightened for this reason (e.g. "other candidates" needs a decision verb,
"unable to offer" only for an interview/position, "regret to inform" needs an outcome word, "cancel your application"
needs a regret frame, "position has been filled" needs the message to be about the user's application).

Note: the Rejected folder is **not** a pure positive set — it also holds the user's own replies, interview
confirmations from the same thread, LinkedIn "Your update from…" mails and acknowledgements (~8% of it).

## Prerequisites
- `.gmail-token.json` must hold all three scopes (readonly, send, modify) — check with
  `python3 -c "import json;print(json.load(open('.gmail-token.json'))['scopes'])"`. Missing `gmail.modify` → 403
  "insufficient authentication scopes"; fix via `gmail-mcp-troubleshooting` (re-auth, tick every checkbox).
- Run scripts from the project root with `.venv/bin/python`. Helper scripts you write go in `scripts/`, never the root.

## Workflow
1. **Confirm the filing convention** (it can change): `scripts/move_emails.py --show-convention`. For this user, filed
   messages carry only `JobApplications/Rejected` — **no Inbox, no parent `JobApplications`**. The MCP
   `move_email` tool only removes INBOX, so use the script.
2. **Find candidates**: `scripts/find_rejections.py --days 45 --out <scratchpad>/new` (widen `--days` if "lately" is
   longer). It downloads all job-related mail (every Gmail tab, no sender filtering), classifies each message and
   prints the verdict and the deciding sentence. `ACTION`/`DELAY` lines are things to leave and tell the user about.
3. **Read every `REJECTION` and `CHECK` line** (the sentence is printed; open the body if in doubt). Move only
   messages that really tell the user they were not selected. Workday daily digests can carry a full rejection.
4. **File, then report**: put the **full** ids (from `emails.json`, not the 8-char prefixes in listings) of every high-confidence `REJECTION`
   - plus any `CHECK` mail you have *read* and found to be a plain rejection - in `ids.json`; mail that needs the user (action, invitation) stays. Run
   `scripts/move_emails.py --ids ids.json` (dry run), then `--apply` (it verifies every message afterwards and writes the
   undo log).
5. **Report** what was filed (company + role + deciding sentence, undo-log path) and what stayed in the inbox and why
   (personality-test-style action items first). **Then update the tracker yourself** (do not offer, do not hand the user a list): run
   `jobtracker-gmail-sync` on just these emails (company **and** title evidence, backup first, apply the clear matches), and
   close out any `interviewing` job whose outcome is now known.
6. **Older unfiled rejections**: the parent label `JobApplications` also holds unfiled rejections (confirmed:
   EY, prosoz, cerence, 1&1 …). To find them: `fetch_gmail_label.py --query 'label:jobapplications
   -label:jobapplications-rejected -in:sent' --out <dir>` then `rejection_classifier.py --emails … --bodies … --show REJECTION`.
   File them under the same rule (high-confidence `REJECTION`), then report and update the tracker.

## Tuning and testing (do this whenever the classifier misjudges something)
- `scripts/test_classifier.py` — regression cases (must stay green; includes ~16 adversarial look-alikes: rescheduling,
  appointment cancellation, job-alert "role filled", salary/parking "unable to offer", referral "other candidates",
  rejection+invitation in one mail). Add the offending sentence first, then fix. **When tuning, a change that raises
  recall but lets one adversarial case through is rejected.**
- `scripts/evaluate_classifier.py --positives <dir with emails.json+bodies.json of Rejected> --negatives <dirs of
  non-rejection mail>` — prints recall (on the author's own folder — deliberately conservative; the rest is replies/confirmations/delays and
  cases sent to `CHECK`; verified: 0 false positives on 1,600 non-rejection mails, and a hand-read sample of 45 positives
  was 45/45 genuine) and every
  flagged negative for review (each is a false positive to fix or an unfiled rejection to offer to move).
- Patterns live in `DECISION` (phrases), `REGRET`+`OUTCOME_NEG` (generic "leider … nicht" tier, vetoed by `VETO`,
  `CONDITIONAL`, `ACTION_REQUEST`, `SCHEDULING`). Prefer adding a narrow phrase or veto over loosening a pattern.
- Patch with Python `str.replace` **plus an `assert old in s`** — silent no-op edits cost an hour once.

## Pitfalls seen
- A first scripted skim dropped a real rejection because it sat in the Promotions tab; read all hits.
- Apostrophes: texts use both `'` and `’`; regexes must accept both. Don't split sentences after dates ("28.07.").
- Gmail search for nested labels uses hyphens: `-label:jobapplications-rejected`. Keep fetches batched
  (quota "Units per minute per user"); big windows with bodies take minutes — run them in the background.
- Don't print or store credentials found in email bodies.
