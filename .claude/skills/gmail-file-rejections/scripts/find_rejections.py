#!/usr/bin/env python3
"""List recent job emails that are rejections and are NOT yet filed in the Rejected label.

Downloads recent job-related mail (all Gmail tabs, no sender filtering), runs the sentence-level
classifier (rejection_classifier.py) and prints a verdict plus the deciding sentence. It never
changes anything.

  .venv/bin/python find_rejections.py --days 45 --out work/new [--label "JobApplications/Rejected"]

Verdicts
  REJECTION  high confidence: a specific decision sentence, no invitation/action request in the message
             (PROPOSE for filing -- still show the user the sentence; see SKILL.md)
  CHECK      doubtful (generic wording, invitation/action in the same message, quote/subject only)
             -> NEVER file without the user reading it. False positives hide real mail; false negatives are fine.
  ACTION     asks the user to do something (test, documents) -> leave in inbox and tell the user
  DELAY      process delayed / still under review -> leave
  (everything else is not printed unless --all; it is confirmations, invitations, newsletters, ...)
Workday daily digests can contain a complete rejection letter: the classifier reads them like any mail.
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rejection_classifier import classify  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=45)
ap.add_argument("--out", required=True)
ap.add_argument("--label", default=os.environ.get("JOBTRACKER_LABEL_PREFIX", "JobApplications") + "/Rejected")
ap.add_argument("--extra", default="", help="extra Gmail query terms")
ap.add_argument("--all", action="store_true", help="also print non-rejections")
ap.add_argument("--max", type=int, default=800)
args = ap.parse_args()

label_q = "-label:" + args.label.lower().replace("/", "-").replace(" ", "-")
jobish = ("bewerbung OR bewerber OR application OR applying OR applicant OR candidate OR candidacy OR stelle OR "
          "position OR vacancy OR sollicitatie OR vacature OR ansökan OR candidature OR recruiting OR hiring")
query = f"newer_than:{args.days}d -in:sent {label_q} ({jobish}) {args.extra}".strip()
fetch = os.path.join(HERE, "..", "..", "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py")
subprocess.run([sys.executable, fetch, "--query", query, "--out", args.out, "--max", str(args.max)],
               check=True, stdout=subprocess.DEVNULL)

emails = json.load(open(f"{args.out}/emails.json"))
bodies = json.load(open(f"{args.out}/bodies.json"))
ACTION = re.compile(r"(nur noch ein schritt|persönlichkeitstest|personality test|please (complete|upload|submit)|bitte (laden|senden|bestätigen|füllen))", re.I)
DELAY = re.compile(r"(verzögert|zwischenstand|still (under|in) review|delay)", re.I)
counts = {}
for x in emails:
    body = bodies.get(x["id"], "")
    r = classify(x["frm"], x["subject"], body)
    verdict = {"REJECTION": "REJECTION", "UNCLEAR": "CHECK"}.get(r["verdict"])  # only REJECTION may be proposed for filing
    if verdict is None:
        verdict = "ACTION" if ACTION.search(body[:700]) else "DELAY" if DELAY.search(x["subject"] + " " + body[:500]) else "other"
    counts[verdict] = counts.get(verdict, 0) + 1
    if verdict != "other" or args.all:
        print(f"## {verdict:9} {x['id']} {x['date'][5:16]} | {x['frm'].split('<')[0][:26]} | {x['subject'][:58]}\n"
              f"     {(r['sentence'] or body[:160])[:200]}  [{r['why']}]\n")
print(counts)
