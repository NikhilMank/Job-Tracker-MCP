#!/usr/bin/env python3
"""Move mails to the Trash by id (never permanent). Dry run unless --apply. Undo log is compatible with
clean_job_suggestions.py --undo.   .venv/bin/python trash_emails.py --ids ids.json [--reason "stale profile warning"] [--apply]"""
import argparse, json, os, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--ids", required=True)
ap.add_argument("--reason", default="")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()
creds = Credentials.from_authorized_user_file(os.path.join(ROOT, ".gmail-token.json"))
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds)
ids = json.load(open(args.ids))
manifest = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "reason": args.reason, "messages": []}
for i in ids:
    m = svc.users().messages().get(userId="me", id=i, format="metadata", metadataHeaders=["Subject", "From"]).execute()
    h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
    manifest["messages"].append(dict(id=i, subject=h.get("Subject", ""), frm=h.get("From", ""), removed_labels=[l for l in m["labelIds"] if l in ("INBOX", "UNREAD")]))
    print("  ", i, "|", h.get("From", "")[:35], "|", h.get("Subject", "")[:70])
if not args.apply:
    raise SystemExit(f"dry run: {len(ids)} mails would go to the Trash -- re-run with --apply")
log_dir = os.path.join(ROOT, "data", "trashed_emails_log"); os.makedirs(log_dir, exist_ok=True)
path = os.path.join(log_dir, time.strftime("%Y%m%d-%H%M%S") + "-profile-warnings.json")
json.dump(manifest, open(path, "w"), ensure_ascii=False, indent=1)
svc.users().messages().batchModify(userId="me", body={"ids": ids, "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}).execute()
print(f"trashed {len(ids)} (recoverable ~30 days). undo: clean_job_suggestions.py --undo {path}")
