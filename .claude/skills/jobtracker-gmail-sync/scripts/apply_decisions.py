#!/usr/bin/env python3
"""Apply match_rejections.py decisions to the tracker DB (dry run unless --apply).

Only touches jobs whose current status is applied/new/interviewing -- NEVER rejected ones.
Backs the DB up (scripts/backup_db.py) before writing and appends an evidence note to each changed job
("Rejected per email YYYY-MM-DD (gmail:<id>) [body-verified]").
Also writes a review CSV of ambiguous emails for the user.

  .venv/bin/python apply_decisions.py --db jobtracker.db --emails work/emails.json \
      --decisions work/decisions.json --review-csv data/rejected_emails_needing_review.csv [--apply]
"""
import argparse, csv, json, os, shutil, sqlite3, time
from email.utils import parsedate_to_datetime

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="jobtracker.db")
ap.add_argument("--emails", required=True)
ap.add_argument("--decisions", required=True)
ap.add_argument("--review-csv")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

def backup_database(db_path: str) -> str:
    """Back up via the project's scripts/backup_db.py (one dated copy per day in backups/, prunes copies older than 30 days).
    Never creates ad-hoc jobtracker.db.bak-* files in the project root (see scripts/README.md)."""
    import subprocess, sys as _sys
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
    if os.path.abspath(db_path) == os.path.join(root, "jobtracker.db"):
        subprocess.run([_sys.executable, os.path.join(root, "scripts", "backup_db.py")], check=True)
        return os.path.join(root, "backups")
    dest = os.path.join(root, "backups", os.path.basename(db_path) + time.strftime("-%Y%m%d-%H%M%S"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy(db_path, dest)
    return dest


emails = {e["id"]: e for e in json.load(open(args.emails))}
decisions = json.load(open(args.decisions))
db = sqlite3.connect(args.db)
jobs = {r[0]: r for r in db.execute("select id,title,company,status from jobs")}


def day(e):
    try:
        return str(parsedate_to_datetime(e["date"]).date())
    except Exception:
        return ""


earliest = {}
for d in decisions:
    if d["cls"] in ("UPDATE", "UPDATE-company"):
        for jid in d.get("jobs") or [d["job"]]:        # "jobs" = all duplicate rows of the same role
            if jobs[jid][3] in ("applied", "new", "interviewing"):
                when = day(emails[d["id"]])
                if jid not in earliest or when < earliest[jid][0]:
                    earliest[jid] = (when, d["id"])

print(f"{len(earliest)} jobs would be marked rejected")
for jid, (when, eid) in sorted(earliest.items(), key=lambda kv: jobs[kv[0]][2]):
    print(f"  {jobs[jid][2][:28]:28} | {jobs[jid][1][:48]:48} | {when} | {emails[eid]['subject'][:40]}")

if args.review_csv:
    with open(args.review_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reason", "from", "subject", "date", "open_jobs_at_company", "gmail_id"])
        for d in decisions:
            if d["cls"] in ("review", "skip-predates") or d["cls"].startswith("review-"):
                open_jobs = [jobs[i] for i in d.get("cands", []) if jobs[i][3] != "rejected"]
                if open_jobs:
                    e = emails[d["id"]]
                    w.writerow([d["cls"], e["frm"], e["subject"], e["date"],
                                " || ".join(f"{j[2]} - {j[1]}" for j in open_jobs[:4]), d["id"]])
    print("review CSV written:", args.review_csv)

if args.apply and earliest:
    backup = backup_database(args.db)
    for jid, (when, eid) in earliest.items():
        db.execute("update jobs set status='rejected', notes=coalesce(notes||char(10),'')||? where id=?",
                   (f"Rejected per email {when} (gmail:{eid}) [body-verified]", jid))
    db.commit()
    print(f"applied. backups in: {backup}")
elif not args.apply:
    print("dry run -- re-run with --apply to write")
