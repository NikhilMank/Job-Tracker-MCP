#!/usr/bin/env python3
"""Move Gmail messages into a label the way the user files them (dry run unless --apply).

Convention discovered for JobApplications/Rejected: filed messages have the target label
and NO Inbox label and NO parent "JobApplications" label. Defaults reproduce that; check
the convention first with --show-convention.

  .venv/bin/python move_emails.py --show-convention
  .venv/bin/python move_emails.py --ids ids.json                 # dry run (ids.json = ["<id>", ...])
  .venv/bin/python move_emails.py --ids ids.json --apply         # move + verify + write an undo log
  .venv/bin/python move_emails.py --undo data/moved_emails_log/<file>.json   # put everything back

Every --apply writes data/moved_emails_log/<timestamp>.json (subject, sender, labels before) so any move
can be reverted -- moving hides mail from the inbox, so it must always be reversible.

Needs the gmail.modify scope; otherwise the API answers 403 "insufficient authentication scopes"
(see gmail-mcp-troubleshooting).
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..")))
import jobtracker_config as _cfg  # saved label_prefix
import argparse, collections, json, os, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ap = argparse.ArgumentParser()
ap.add_argument("--ids")
ap.add_argument("--to", default=_cfg.label_prefix() + "/Rejected")
ap.add_argument("--also-add", action="append", default=[], help="extra labels to add (e.g. JobApplications/EasyApply)")
ap.add_argument("--remove", action="append", default=None, help="labels to remove (default: INBOX + parent of --to)")
ap.add_argument("--token", default=".gmail-token.json")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--show-convention", action="store_true")
ap.add_argument("--undo", help="manifest written by an earlier --apply")
ap.add_argument("--log-dir", default="data/moved_emails_log")
args = ap.parse_args()

creds = Credentials.from_authorized_user_file(args.token)
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds)
labels = svc.users().labels().list(userId="me").execute()["labels"]
by_name = {l["name"].lower(): l["id"] for l in labels}
name_of = {l["id"]: l["name"] for l in labels}


def lid(name):
    if name.lower() not in by_name:
        raise SystemExit(f"Unknown label {name!r}")
    return by_name[name.lower()]


target = lid(args.to)
parent = args.to.rsplit("/", 1)[0] if "/" in args.to else None
remove = args.remove if args.remove is not None else ["INBOX"] + ([parent] if parent else [])
extra_ids = [lid(x) for x in args.also_add]
add_ids = [target] + extra_ids
remove_ids = [lid(r) if r.upper() != "INBOX" else "INBOX" for r in remove]

if args.show_convention:
    ids = [m["id"] for m in svc.users().messages().list(userId="me", labelIds=[target], maxResults=40).execute().get("messages", [])]
    c = collections.Counter()
    for i in ids:
        for l in svc.users().messages().get(userId="me", id=i, format="minimal").execute()["labelIds"]:
            c[name_of.get(l, l)] += 1
    print(f"label counts over the {len(ids)} newest messages in {args.to}:", dict(c))
    raise SystemExit

if args.undo:
    log = json.load(open(args.undo))
    restore = collections.defaultdict(list)
    for m in log["messages"]:
        restore[(tuple(sorted(m["removed_labels"])), tuple(sorted(m.get("added_labels", [log["target"]]))))].append(m["id"])
    for (removed, added), ids_ in restore.items():
        svc.users().messages().batchModify(userId="me", body={"ids": ids_, "addLabelIds": list(removed),
                                                              "removeLabelIds": list(added)}).execute()
        print(f"restored {len(ids_)} messages -> re-added {[name_of.get(r, r) for r in removed]}, removed {[name_of.get(a, a) for a in added]}")
    raise SystemExit

if "https://www.googleapis.com/auth/gmail.modify" not in (creds.scopes or []):
    raise SystemExit("Token lacks gmail.modify -> re-run gmail_mcp.py --auth and tick ALL checkboxes.")
ids = json.load(open(args.ids))
print(f"{len(ids)} messages: add {[args.to] + args.also_add}; remove {remove}")
if not args.apply:
    raise SystemExit("dry run -- re-run with --apply")
manifest = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "target": target, "added": add_ids, "messages": []}
for i in ids:
    m = svc.users().messages().get(userId="me", id=i, format="metadata", metadataHeaders=["Subject", "From"]).execute()
    h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
    had = set(m["labelIds"])
    manifest["messages"].append(dict(id=i, subject=h.get("Subject", ""), frm=h.get("From", ""),
                                     removed_labels=[r for r in remove_ids if r in had],
                                     added_labels=[a for a in add_ids if a not in had]))
os.makedirs(args.log_dir, exist_ok=True)
log_path = os.path.join(args.log_dir, time.strftime("%Y%m%d-%H%M%S") + ".json")
json.dump(manifest, open(log_path, "w"), ensure_ascii=False, indent=1)
svc.users().messages().batchModify(userId="me", body={"ids": ids, "addLabelIds": add_ids, "removeLabelIds": remove_ids}).execute()
print("undo log:", log_path, "  (undo with --undo)")
bad = []
for i in ids:
    l = svc.users().messages().get(userId="me", id=i, format="minimal").execute()["labelIds"]
    if any(a not in l for a in add_ids) or any(r in l for r in remove_ids):
        bad.append(i)
print(f"moved {len(ids)}; verification failures: {len(bad)}", bad)
