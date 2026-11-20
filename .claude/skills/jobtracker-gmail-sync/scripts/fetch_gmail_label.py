#!/usr/bin/env python3
"""Download emails (headers + snippet + text body) from a Gmail label or search query.

Resumable, batched and throttled: Gmail's per-minute quota ("Units per minute per
user") is hit quickly by one-request-per-message loops, so this uses batch requests,
sleeps between batches, retries with backoff and saves progress after every batch.

Usage (run from the project root, with the project venv):
  .venv/bin/python <skill>/scripts/fetch_gmail_label.py --label "JobApplications/Rejected" --out work/
  .venv/bin/python <skill>/scripts/fetch_gmail_label.py --query 'after:2026/01/01 -in:sent "Einladung"' --out work/ --no-bodies

Outputs in --out:  emails.json  (list of {id, subject, frm, date, snippet, labels})
                   bodies.json  (id -> first 3000 chars of plain text, unless --no-bodies)
Run it in the background for big labels (2,500 emails with bodies takes ~10-15 min).
"""
import argparse, base64, html, json, os, re, time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ap = argparse.ArgumentParser()
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--label", help="Label name, e.g. 'JobApplications/Rejected'")
g.add_argument("--query", help="Gmail search query")
ap.add_argument("--out", required=True)
ap.add_argument("--token", default=".gmail-token.json")
ap.add_argument("--no-bodies", action="store_true")
ap.add_argument("--extra-ids", help="JSON file with extra message ids to download in addition to the query (e.g. pending items from mail_state)")
ap.add_argument("--body-chars", type=int, default=5000, help="how much of each body to keep")
ap.add_argument("--max", type=int, default=0, help="stop listing after N messages (0 = all)")
ap.add_argument("--batch", type=int, default=20)
ap.add_argument("--pause", type=float, default=3.0)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

creds = Credentials.from_authorized_user_file(args.token)
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds)


def retry(fn, tries=10):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # quota errors surface as HttpError 403/429
            print(f"retry {i + 1}: {str(e)[:80]}", flush=True)
            time.sleep(15 * (i + 1))
    raise SystemExit("giving up after repeated errors")


kw = {}
if args.label:
    labels = retry(lambda: svc.users().labels().list(userId="me").execute())["labels"]
    by_name = {l["name"].lower(): l["id"] for l in labels}
    if args.label.lower() not in by_name:
        raise SystemExit(f"Unknown label {args.label!r}. Known: {sorted(by_name)}")
    kw["labelIds"] = [by_name[args.label.lower()]]
else:
    kw["q"] = args.query

ids, tok = [], None
while True:
    r = retry(lambda: svc.users().messages().list(userId="me", maxResults=500, pageToken=tok, **kw).execute())
    ids += [m["id"] for m in r.get("messages", [])]
    tok = r.get("nextPageToken")
    if not tok or (args.max and len(ids) >= args.max):
        break
if args.max:
    ids = ids[:args.max]
if args.extra_ids:
    ids += [i for i in json.load(open(args.extra_ids)) if i not in set(ids)]
print(len(ids), "messages", flush=True)

EP, BP = f"{args.out}/emails.json", f"{args.out}/bodies.json"
emails = {e["id"]: e for e in json.load(open(EP))} if os.path.exists(EP) else {}
bodies = json.load(open(BP)) if os.path.exists(BP) else {}


def text_of(part, out):
    if part["body"].get("data") and part.get("mimeType", "").startswith("text/"):
        t = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
        if "html" in part["mimeType"]:
            t = re.sub(r"<(style|script).*?</\1>", "", t, flags=re.S)
            t = re.sub(r"<[^>]+>", " ", t)
        out.append(t)
    for p in part.get("parts", []) or []:
        text_of(p, out)


def on_msg(rid, resp, exc):
    if exc is not None:
        return
    h = {x["name"]: x["value"] for x in resp["payload"]["headers"]}
    emails[rid] = dict(id=rid, subject=h.get("Subject", ""), frm=h.get("From", ""),
                       date=h.get("Date", ""), snippet=resp.get("snippet", ""),
                       labels=resp.get("labelIds", []))
    if not args.no_bodies:
        out = []
        text_of(resp["payload"], out)
        # LinkedIn notification mails put ~3000 chars of invisible preheader padding and link footers before the decision
        # sentence ("we will not be moving forward"); strip the invisible characters so it stays inside the kept text
        text = re.sub("[\u00ad\u034f\u061c\u180e\u200b-\u200f\u2060-\u2064\ufeff]", "", html.unescape(" ".join(out)))
        bodies[rid] = re.sub(r"\s+", " ", text)[:args.body_chars]


todo = [i for i in ids if i not in emails or (not args.no_bodies and i not in bodies)]
fmt = "metadata" if args.no_bodies else "full"
for k in range(0, len(todo), args.batch):
    chunk = todo[k:k + args.batch]
    for attempt in range(8):
        b = svc.new_batch_http_request(callback=on_msg)
        for i in chunk:
            if i not in emails or (not args.no_bodies and i not in bodies):
                params = dict(userId="me", id=i, format=fmt)
                if fmt == "metadata":
                    params["metadataHeaders"] = ["Subject", "From", "Date"]
                b.add(svc.users().messages().get(**params), request_id=i)
        b.execute()
        if all(i in emails for i in chunk):
            break
        time.sleep(12 * (attempt + 1))
    json.dump(list(emails.values()), open(EP, "w"), ensure_ascii=False)
    json.dump(bodies, open(BP, "w"), ensure_ascii=False)
    print(f"{len(emails)}/{len(ids)}", flush=True)
    time.sleep(args.pause)

json.dump([emails[i] for i in ids if i in emails], open(EP, "w"), ensure_ascii=False)
print("DONE", len(emails), flush=True)
