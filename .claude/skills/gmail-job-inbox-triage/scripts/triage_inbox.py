#!/usr/bin/env python3
"""One pass over the job-related inbox: classify every mail and write ready-to-review move lists. READ-ONLY.

  .venv/bin/python triage_inbox.py --days 30 --out <scratchpad>/triage          # downloads, classifies, reports
  .venv/bin/python triage_inbox.py --out <scratchpad>/triage --no-fetch          # re-classify what was downloaded

Buckets (precision first -- nothing is ever moved by this script):
  SHORTLISTED positive reply: interview invitation, assessment invitation, shortlisted / next stage, offer. Shown FIRST.
              Standing rule: star it + label JobApplications/Shortlisted (mark_shortlisted.py; it STAYS in the inbox)
              + set the tracker job to `interviewing` (`offer` for an offer) when company AND title match.
  NEEDS_YOU   request to act (personality test, documents, e-mail confirmation, draft application, profile to complete).
              Shown right after SHORTLISTED. Always stays in the inbox. Once the user has
              handled one they add the label JobApplications/Attended and it is skipped from then on.
  STALE_PROFILE "we will delete your profile because of inactivity -- log in to keep it". Standing rule: trash (trash_emails.py).
  REJECTION   rejection_classifier says REJECTION  -> candidate list for JobApplications/Rejected
  CONFIRM     plain receipt (confirmation_classifier) -> JobApplications
  CONFIRM_EASY LinkedIn Easy Apply receipt           -> JobApplications + JobApplications/EasyApply
  DOUBTFUL    acknowledgement or rejection wording, but something else is in the mail -> READ before deciding
  UNCLASSIFIED job-related mail from a non-platform sender that matched NO rule (new wording, odd subject, ATS mail). READ it:
              most are plain receipts, some are rejections or invitations the patterns do not know yet. These ids stay
              "pending" until they are filed, so they come back on the next run.
  (everything else -- marketing, platform alerts, private mail -- is not listed)
Writes <out>/plan.json and ids files: rejected.json, confirm.json, confirm_easy.json (candidate lists, to be approved).
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(SK, "gmail-file-rejections", "scripts"))
sys.path.insert(0, os.path.join(SK, "gmail-file-applications", "scripts"))

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="auto", help="auto = only mail newer than the last committed run (+ pending items) | all | N days")
ap.add_argument("--out", required=True)
ap.add_argument("--no-fetch", action="store_true")
ap.add_argument("--commit", action="store_true", help="save the run time + unresolved ids (do this AFTER reporting to the user)")
ap.add_argument("--parent", default=os.environ.get("JOBTRACKER_LABEL_PREFIX", "JobApplications"))
ap.add_argument("--max", type=int, default=800)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

sys.path.insert(0, HERE)
from mail_state import since_query, pending_ids, commit  # noqa: E402
from triage_rules import triage_one  # noqa: E402
TASK = "job_inbox_triage"
since, started = since_query(TASK, default_days=30, mode=args.since)
if not args.no_fetch:
    query = f"in:inbox -label:{args.parent.lower()} -label:{args.parent.lower()}-shortlisted {since} -in:sent".replace("  ", " ")
    cmd = [sys.executable, os.path.join(SK, "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py"),
           "--query", query, "--out", args.out, "--max", str(args.max)]
    pend = pending_ids(TASK)   # mails left unresolved last time are re-read no matter how old they are
    if pend:
        json.dump(pend, open(f"{args.out}/pending_in.json", "w"))
        cmd += ["--extra-ids", f"{args.out}/pending_in.json"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
elif os.path.exists(f"{args.out}/emails.json"):
    started = int(os.path.getmtime(f"{args.out}/emails.json")) - 7200   # never record a time later than the download
# pending mails that have since been filed / deleted are dropped (only mail still in the inbox and unfiled counts)
emails = json.load(open(f"{args.out}/emails.json"))
bodies = json.load(open(f"{args.out}/bodies.json"))
emails = [e for e in emails if "INBOX" in e.get("labels", ["INBOX"])]   # drops pending ids that have since been filed/deleted
# mails the user marked with the label JobApplications/Attended are handled: do not remind about them again
from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
_creds = Credentials.from_authorized_user_file(os.path.join(HERE, "..", "..", "..", "..", ".gmail-token.json"))
if not _creds.valid:
    _creds.refresh(Request())
_attended = {l["id"] for l in build("gmail", "v1", credentials=_creds).users().labels().list(userId="me").execute()["labels"]
             if l["name"].lower() == f"{args.parent.lower()}/attended"}
# the label sits on ONE message, so a later reply in the same thread (a new message without the label) is still triaged normally
handled = [e for e in emails if _attended & set(e.get("labels", []))]
emails = [e for e in emails if not _attended & set(e.get("labels", []))]
if handled:
    print(f"\n{len(handled)} mails already dealt with (label Attended), skipped")

buckets = {"SHORTLISTED": [], "NEEDS_YOU": [], "STALE_PROFILE": [], "REJECTION": [], "CONFIRM": [], "CONFIRM_EASY": [], "DOUBTFUL": [], "UNCLASSIFIED": []}
for e in emails:
    bucket, note = triage_one(e, bodies.get(e["id"], ""))
    if bucket:
        buckets[bucket].append((e, note))

for name in ("SHORTLISTED", "NEEDS_YOU", "STALE_PROFILE", "REJECTION", "CONFIRM_EASY", "CONFIRM", "DOUBTFUL", "UNCLASSIFIED"):
    rows = sorted(buckets[name], key=lambda x: x[0]["date"], reverse=True)
    print(f"\n== {name}: {len(rows)} ==")
    for e, note in rows:
        print(f"  {e['id']} {e['date'][5:16]} | {e['frm'].split('<')[0][:22]:22} | {e['subject'][:46]:46} | {note[:64]}")

plan = {k: [e["id"] for e, _ in v] for k, v in buckets.items()}
json.dump(plan, open(f"{args.out}/plan.json", "w"), indent=1)
for fname, key in (("shortlisted.json", "SHORTLISTED"), ("stale_profile.json", "STALE_PROFILE"), ("rejected.json", "REJECTION"), ("confirm.json", "CONFIRM"), ("confirm_easy.json", "CONFIRM_EASY")):
    json.dump(plan[key], open(f"{args.out}/{fname}", "w"))
if args.commit:
    unresolved = plan["NEEDS_YOU"] + plan["STALE_PROFILE"] + plan["DOUBTFUL"] + plan["REJECTION"] + plan["UNCLASSIFIED"]
    commit(TASK, started, pending=unresolved)
    print(f"saved run time {time.strftime('%Y-%m-%d %H:%M', time.localtime(started))} and {len(unresolved)} unresolved ids for the next run")
print(f"\nCandidate id lists written to {args.out}/ (rejected.json, confirm.json, confirm_easy.json) -- candidates only, nothing moved.")
