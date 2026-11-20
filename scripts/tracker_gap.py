#!/usr/bin/env python3
"""Which applications have a LinkedIn Easy Apply receipt in Gmail but no matching job in jobtracker.db?  READ-ONLY.

  .venv/bin/python scripts/tracker_gap.py --days 14 [--out <scratchpad>/gap]

Parses "Alex, your application was sent to <Company>" + the job title from the receipt body, then looks for a job whose
company contains the company name and whose title shares its first words. Prints the receipts with no match: those are jobs
the user applied to but never pasted into data/todays_jobs.md. Writes nothing to the DB or Gmail.
"""
import argparse, json, os, re, sqlite3, subprocess, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=14)
ap.add_argument("--out", default=None)
ap.add_argument("--no-fetch", action="store_true")
args = ap.parse_args()
out = args.out or tempfile.mkdtemp(prefix="gap_")
if not args.no_fetch:
    q = f'from:jobs-noreply@linkedin.com subject:"your application was sent to" newer_than:{args.days}d in:anywhere'
    subprocess.run([sys.executable, os.path.join(ROOT, ".claude", "skills", "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py"),
                    "--query", q, "--out", out, "--max", "400"], check=True, stdout=subprocess.DEVNULL, cwd=ROOT)
emails = json.load(open(f"{out}/emails.json"))
bodies = json.load(open(f"{out}/bodies.json"))
norm = lambda t: re.sub(r"[^a-z0-9äöüß]+", " ", (t or "").lower()).strip()
db = sqlite3.connect(os.path.join(ROOT, "jobtracker.db"))
jobs = [(i, norm(t), norm(c), st) for i, t, c, st in db.execute("select id,title,company,status from jobs")]

missing, found = [], 0
for e in emails:
    m = re.search(r"application was sent to (.+)$", e["subject"].strip(), re.I)
    if not m:
        continue
    company = m.group(1).strip()
    body = re.sub(r"\s+", " ", bodies.get(e["id"], ""))
    t = re.search(r"application was sent to " + re.escape(company) + r"\s+(.+?)\s+" + re.escape(company), body, re.I)
    title = t.group(1).strip() if t else ""
    nc, nt = norm(company), norm(title)
    first = " ".join(nt.split()[:3])
    hit = [j for j in jobs if nc and (nc in j[2] or j[2] in nc) and (not first or first in j[1] or j[1][:20] in nt)]
    if hit:
        found += 1
    else:
        missing.append((e["date"][:16], company, title or "(title not parsed)", e["id"]))
print(f"{found} receipts matched a tracker entry, {len(missing)} did not:")
for d, c, t, i in sorted(missing):
    print(f"  {d} | {c} | {t} | {i}")
