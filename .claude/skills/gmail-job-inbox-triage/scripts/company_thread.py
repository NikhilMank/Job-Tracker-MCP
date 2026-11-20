"""List every mail with a company, BOTH directions (inbox, sent, labelled, archived), oldest first.

Read-only. Use it for the interview-notes step of the daily routine: a task the user has done shows up as a SENT mail,
which an inbox-only search never finds (e.g. a coding challenge you already answered by mail).

    .venv/bin/python .claude/skills/gmail-job-inbox-triage/scripts/company_thread.py Acme [Globex ...] [--days 45] [--text]
"""
import argparse, base64, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ap = argparse.ArgumentParser()
ap.add_argument("names", nargs="+")
ap.add_argument("--days", type=int, default=45)
ap.add_argument("--text", action="store_true", help="also print the first 400 chars of each mail's own text")
a = ap.parse_args()
g = build("gmail", "v1", credentials=Credentials.from_authorized_user_file(os.path.join(ROOT, ".gmail-token.json")))


def plain(p, out):
    if p["mimeType"] == "text/plain" and p.get("body", {}).get("data"):
        out.append(base64.urlsafe_b64decode(p["body"]["data"]).decode("utf8", "ignore"))
    for x in p.get("parts", []):
        plain(x, out)


def files(p):
    r = [p["filename"]] if p.get("filename") else []
    for x in p.get("parts", []):
        r += files(x)
    return r


for name in a.names:
    q = f'(from:{name} OR to:{name} OR "{name}") newer_than:{a.days}d'
    ids, tok = [], None
    while True:
        r = g.users().messages().list(userId="me", q=q, maxResults=100, pageToken=tok, includeSpamTrash=False).execute()
        ids += [m["id"] for m in r.get("messages", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    rows = []
    for i in ids:
        m = g.users().messages().get(userId="me", id=i, format="full").execute()
        h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
        rows.append((int(m["internalDate"]), i, "SENT" if "SENT" in m["labelIds"] else "recv", h.get("Date", "")[:22],
                     h.get("From", "")[:28], h.get("To", "")[:28], h.get("Subject", "")[:60], files(m["payload"]), m))
    print(f"== {name}: {len(rows)} mails in {a.days} days (oldest first)")
    for _, i, d, date, frm, to, subj, fl, m in sorted(rows):
        print(f"{date} {d} {i} | {frm} -> {to} | {subj}" + (f" | attach: {', '.join(fl)}" if fl else ""))
        if a.text:
            o = []; plain(m["payload"], o)
            print("    " + " ".join((o[0] if o else "").split())[:400])
