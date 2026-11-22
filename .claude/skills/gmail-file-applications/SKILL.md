---
name: gmail-file-applications
description: File job-application confirmation emails ("we received your application", LinkedIn Easy Apply receipts) out of the Gmail inbox into the user's JobApplications label; LinkedIn Easy Apply receipts also get JobApplications/EasyApply. Use when the user says they applied for jobs and wants the confirmation emails sorted/moved, or asks to clean the inbox of application receipts. Precision first - never hide a rejection, interview invitation or request that needs the user.
---

# File application confirmations into `JobApplications`

## Convention (verified on the user's mailbox)
- Plain confirmation → label **`JobApplications`** only, **no Inbox**. There is no `JobApplications/Applied`
  label — the user once said so by mistake; the parent label *is* the "applied" folder.
- LinkedIn Easy Apply receipt (sender `jobs-noreply@linkedin.com`, subject "Alex, your application was sent to <Company>")
  → `JobApplications` **and** `JobApplications/EasyApply`, no Inbox.
- **EasyApply = LinkedIn only** (verified: 569/569 messages in that label are from linkedin.com). Indeed and Stepstone
  receipts are filed under `JobApplications` only (159 / 85 existing ones carry no EasyApply). Always check sender before
  adding the EasyApply label.
- Rejections go to `JobApplications/Rejected` (skill `gmail-file-rejections`), never here.
- Check it again with `gmail-file-rejections/scripts/move_emails.py --show-convention --to JobApplications/EasyApply`.

## Principle: precision over recall
Filing receipts out of the inbox only happens if the `file_receipts` preference in `data/routine-preferences.md` is `yes` (asked once by `daily-job-routine`; if it is not set, ask first).

Filing a mail out of the inbox hides it. A false positive (a rejection, interview invite or request filed as a receipt) is
dangerous; leaving a receipt in the inbox costs nothing. Real data showed the danger: of mails in the user's Rejected folder
that *looked* like receipts, several were rejections ("we are unable to offer you this position", "we need a higher German
level", "not able to pursue your application"), one was an interview invitation, one a soft rejection ("only the candidates in
the engere Wahl…"). So a mail is a confirmation **only if** an acknowledgement sentence is present AND all of this holds:
- the rejection classifier says NOT_REJECTION, and no *risk wording* appears anywhere (unfortunately/leider/regret, unable /
  not able / cannot / won't, however/jedoch/allerdings, requirement wording (benötigen/requires/proficiency), filled /
  besetzt / discontinued, other candidates / Kandidat:innen, engere Wahl / shortlist, talent pool, "update on your
  application", ...),
- no interview/invitation/appointment wording at all (einladen, interview, Gespräch, Termin, Zoom, Telefon ...),
- no request for the candidate to act (please send/upload/confirm, assessment/test, deadline, missing documents,
  salary expectation, verify e-mail ...), no newsletter/job-alert footer, and the message is short (< 1,800 chars).
Easy Apply receipts are exempt from the footer/length checks (their text is fixed) but not from the rejection checks.
Everything else with an acknowledgement sentence is `DOUBTFUL`: read it, never file it automatically.

## Workflow
1. Prerequisites: `.gmail-token.json` has `gmail.modify` (see `gmail-mcp-troubleshooting`).
2. `scripts/find_confirmations.py --days 30 --out <scratchpad>/inb` (read-only). It prints `PROPOSE`, `DOUBTFUL` (with the
   reason) and `REJECTION` (belongs in Rejected).
3. **Read the `DOUBTFUL` ones** (the matched context is easy to print). Typical harmless triggers: "Telefon" in a signature,
   "kurzfristig" (matches "frist"), "don't forget", "etwas Zeit benötigen", "leiten Sie nicht weiter", Stepstone's
   "apply to similar jobs" footer. Typical real ones: rejections hiding in a polite text, "please confirm your e-mail",
   "send us a certificate", survey requests. Build the explicit approved id list yourself.
4. File the high-confidence `PROPOSE` ids right away, plus the `DOUBTFUL` ones you have **read** and found to be plain receipts (the
   user wants you to settle these yourself, not to verify them; list them in the report). Anything that needs the user (action,
   invitation, e-mail confirmation) stays in the inbox. Use full ids from `emails.json`.
   - Easy Apply: `move_emails.py --ids easy.json --to JobApplications --also-add JobApplications/EasyApply --apply`
   - others: `move_emails.py --ids plain.json --to JobApplications --apply`
   (dry run first; the script verifies and writes an undo log in `data/moved_emails_log/`; `--undo <log>` restores.)
5. Report: moved counts (+ log paths), what stayed and why — especially mails that need the user (e-mail confirmations,
   document requests, tests) and any rejections found (file them via `gmail-file-rejections`, then update the tracker).

## Testing / tuning
- `scripts/test_confirmation.py` (must stay green; every NOT case is a real near-miss) and, for measurement, run
  `confirmation_classifier.py --emails … --bodies …` on (a) the user's filed confirmations (recall; ≈45% auto-proposed, rest
  DOUBTFUL by design) and (b) the Rejected folder (must yield only genuine receipts: 3/2,492 after tuning, all verified).
- To add recall, add acknowledgement *phrases* to `CONFIRM`; never relax `RISK`/`ACTION`/`INVITE` to gain recall.
- Bodies are fetched truncated (3,000 chars); long mails are DOUBTFUL for that reason.
- Helper scripts go in `scripts/`, never the project root.
