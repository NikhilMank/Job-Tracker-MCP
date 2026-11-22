#!/usr/bin/env python3
"""Mark positive replies (interview invitation, assessment invitation, shortlisted, offer): star them and add the label
JobApplications/Shortlisted. The mail STAYS IN THE INBOX (user's rule: "don't move it, I want to see it when I open the mail").
Dry run unless --apply. Writes an undo log compatible with gmail-file-rejections/scripts/move_emails.py --undo.

  .venv/bin/python mark_shortlisted.py --ids ids.json            # dry run
  .venv/bin/python mark_shortlisted.py --ids ids.json --apply
  ... --no-star      only the label
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..")))
import jobtracker_config as _cfg  # saved label_prefix
import argparse, json, os, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
LABEL = _cfg.label_prefix() + "/Shortlisted"
ap = argparse.ArgumentParser()
ap.add_argument("--ids", required=True)
ap.add_argument("--apply", action="store_true")
ap.add_argument("--no-star", action="store_true")
args = ap.parse_args()
creds = Credentials.from_authorized_user_file(os.path.join(ROOT, ".gmail-token.json"))
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds)
labels = {l["name"].lower(): l["id"] for l in svc.users().labels().list(userId="me").execute()["labels"]}
if LABEL.lower() not in labels:
    if not args.apply:
        print(f"label {LABEL!r} does not exist yet; --apply would create it")
        labels[LABEL.lower()] = "NEW"
    else:
        labels[LABEL.lower()] = svc.users().labels().create(userId="me", body={"name": LABEL, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).execute()["id"]
add = [labels[LABEL.lower()]] + ([] if args.no_star else ["STARRED"])
ids = json.load(open(args.ids))
print(f"{len(ids)} messages: add label {LABEL}" + ("" if args.no_star else " + star") + "; Inbox label is NOT touched")
manifest = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "target": add[0], "added": add, "messages": []}
for i in ids:
    m = svc.users().messages().get(userId="me", id=i, format="metadata", metadataHeaders=["Subject", "From"]).execute()
    h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
    manifest["messages"].append(dict(id=i, subject=h.get("Subject", ""), frm=h.get("From", ""), removed_labels=[],
                                     added_labels=[a for a in add if a not in m["labelIds"]], in_inbox="INBOX" in m["labelIds"]))
    print("  ", i, "|", h.get("From", "")[:35], "|", h.get("Subject", "")[:60], "| inbox:", "INBOX" in m["labelIds"])
if not args.apply:
    raise SystemExit("dry run -- re-run with --apply")
log_dir = os.path.join(ROOT, "data", "moved_emails_log"); os.makedirs(log_dir, exist_ok=True)
path = os.path.join(log_dir, time.strftime("%Y%m%d-%H%M%S") + "-shortlisted.json")
json.dump(manifest, open(path, "w"), ensure_ascii=False, indent=1)
svc.users().messages().batchModify(userId="me", body={"ids": ids, "addLabelIds": add}).execute()
bad = [i for i in ids if any(a not in svc.users().messages().get(userId="me", id=i, format="minimal").execute()["labelIds"] for a in add)
       or "INBOX" not in svc.users().messages().get(userId="me", id=i, format="minimal").execute()["labelIds"] and manifest["messages"][ids.index(i)]["in_inbox"]]
print(f"done; undo log {path}; verification failures: {bad}")
