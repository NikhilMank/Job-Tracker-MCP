#!/usr/bin/env python3
"""List application-confirmation emails still sitting in the inbox (read-only).

  .venv/bin/python find_confirmations.py --days 30 --out <scratchpad>/inb

Downloads recent inbox mail that is not yet filed under the parent label, classifies it and prints
  PROPOSE   plain acknowledgement, nothing else in the message  (E = LinkedIn Easy Apply -> also needs the EasyApply label)
  DOUBTFUL  an acknowledgement sentence is there but something else is too (rejection wording, interview
            invitation, request to act, newsletter footer, long text). READ these; most are fine receipts
            that tripped a keyword (signature "Telefon", "kurzfristig", ...), some are rejections or need the user.
  REJECTION a rejection (rejection_classifier) -> belongs in JobApplications/Rejected, not here
Precision first: PROPOSE is deliberately conservative; nothing is ever moved by this script.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..")))
import jobtracker_config as _cfg  # saved label_prefix
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "gmail-file-rejections", "scripts"))
from confirmation_classifier import classify_confirmation  # noqa: E402
from rejection_classifier import classify as classify_rejection  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=30)
ap.add_argument("--out", required=True)
ap.add_argument("--parent", default=_cfg.label_prefix())
ap.add_argument("--max", type=int, default=800)
args = ap.parse_args()

query = f"in:inbox -label:{args.parent.lower()} newer_than:{args.days}d -in:sent"
fetch = os.path.join(HERE, "..", "..", "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py")
subprocess.run([sys.executable, fetch, "--query", query, "--out", args.out, "--max", str(args.max)], check=True, stdout=subprocess.DEVNULL)
emails = json.load(open(f"{args.out}/emails.json"))
bodies = json.load(open(f"{args.out}/bodies.json"))

rows = {"PROPOSE": [], "DOUBTFUL": [], "REJECTION": []}
for e in emails:
    body = bodies.get(e["id"], "")
    rej = classify_rejection(e["frm"], e["subject"], body)
    if rej["verdict"] == "REJECTION":
        rows["REJECTION"].append((e, rej["sentence"]))
        continue
    c = classify_confirmation(e["frm"], e["subject"], body)
    if c["verdict"] == "CONFIRMATION":
        rows["PROPOSE"].append((e, ("E " if c["easyapply"] else "  ") + c["sentence"]))
    elif c["verdict"] == "UNCLEAR":
        rows["DOUBTFUL"].append((e, c["why"]))
for k, v in rows.items():
    print(f"\n== {k}: {len(v)} ==")
    for e, note in sorted(v, key=lambda x: x[0]["date"]):
        print(f"  {e['id']} {e['date'][5:16]} | {e['frm'].split('<')[0][:24]:24} | {e['subject'][:50]:50} | {note[:70]}")
