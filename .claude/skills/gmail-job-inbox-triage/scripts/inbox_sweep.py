"""List EVERY mail in `in:inbox newer_than:<days>d` (id, NeedsAttention flag, date, From, Subject). Read-only. Step 5d of daily-job-routine.

    .venv/bin/python .claude/skills/gmail-job-inbox-triage/scripts/inbox_sweep.py [--days 21] [--hide-noise]
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..")))
import jobtracker_config as _cfg  # saved label_prefix
import argparse, os, re
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=21); ap.add_argument("--hide-noise", action="store_true")
a = ap.parse_args()
NOISE = re.compile(os.environ.get("JOBTRACKER_SWEEP_NOISE", r"newsletter|no-?reply@.*(shop|store)|unsubscribe"), re.I)  # --hide-noise filter; override via env
g = build("gmail", "v1", credentials=Credentials.from_authorized_user_file(os.path.join(ROOT, ".gmail-token.json")))
LABEL_PREFIX = _cfg.label_prefix()
NA_ID = next((l["id"] for l in g.users().labels().list(userId="me").execute()["labels"] if l["name"].lower() == (LABEL_PREFIX + "/NeedsAttention").lower()), None)
ids, tok = [], None
while True:
    r = g.users().messages().list(userId="me", q=f"in:inbox newer_than:{a.days}d", maxResults=200, pageToken=tok).execute()
    ids += [m["id"] for m in r.get("messages", [])]; tok = r.get("nextPageToken")
    if not tok: break
n = 0
for i in ids:
    m = g.users().messages().get(userId="me", id=i, format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
    h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
    line = f"{i} {'NA' if NA_ID in m.get('labelIds', []) else '  '} {h.get('Date','')[5:16]} | {h.get('From','')[:30]} | {h.get('Subject','')[:70]}"
    if a.hide_noise and NOISE.search(line): continue
    print(line); n += 1
print(f"{n} shown of {len(ids)}")
