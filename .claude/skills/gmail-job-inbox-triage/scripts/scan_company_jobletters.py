#!/usr/bin/env python3
"""Read company job-agent letters (SuccessFactors/jobs2web style mailers) and list AI-related roles.

  .venv/bin/python scan_company_jobletters.py --out <scratchpad>/cjl --since all [--recent-days 120]
  .venv/bin/python scan_company_jobletters.py --out <scratchpad>/cjl            # later runs: only mail newer than the last run

Read-only by default. --trash moves the scanned letters to the Trash, but ONLY when the user has said so (report the AI
roles first, then wait for their go-ahead -- every time). Undo: clean_job_suggestions.py --undo <log>. Titles are cut out of each letter's run-on job list around AI/ML
keywords. The letter preamble is removed first, because it repeats the user's OWN saved search name ("Data Scientist,
Luxembourg") and would otherwise create false hits. Output: company -> role titles (first/last seen).
State (task "company_jobletters" in data/job_mail_state.json) is committed with --commit after the user has seen the report.
"""
import argparse, collections, json, os, re, subprocess, sys, time
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mail_state import since_query, commit  # noqa: E402

TASK = "company_jobletters"
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--since", default="auto")
ap.add_argument("--recent-days", type=int, default=120, help="only report letters from the last N days (older jobs are usually gone)")
ap.add_argument("--no-fetch", action="store_true")
ap.add_argument("--commit", action="store_true", help="save the run time (do this after reporting to the user)")
ap.add_argument("--trash", action="store_true", help="move the scanned letters to the Trash, ONLY if the user\'s company_job_letters preference is trash-all or they said so for this run; writes an undo log")
ap.add_argument("--trash-no-ai", action="store_true", help="only when the user\'s company_job_letters preference is trash-unless-matching-role: trash letters WITHOUT a matching role; letters with one are kept and printed")
ap.add_argument("--also-related", action="store_true", help="also list Data Engineer / Data Architect / Cloud-ML platform roles")
args = ap.parse_args()

since, started = since_query(TASK, default_days=120, mode=args.since)
q = ('(from:jobnotification OR from:jobabo OR from:jobs2web OR subject:"new jobs posted" OR subject:"Neue Stellen" OR subject:"New jobs available" '
     'OR subject:"neue, spannende Stellen" OR subject:"Neue von jobs" OR subject:"veröffentlichte Stellen" OR subject:"Job Alert Notification") '
     f'-in:sent -in:trash -label:{os.environ.get("JOBTRACKER_LABEL_PREFIX", "JobApplications").lower()} {since}').strip()
if not args.no_fetch:
    subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py"),
                    "--query", q, "--body-chars", "12000", "--max", "800", "--out", args.out], check=True, stdout=subprocess.DEVNULL)
elif os.path.exists(f"{args.out}/emails.json"):
    started = int(os.path.getmtime(f"{args.out}/emails.json")) - 7200
emails = json.load(open(f"{args.out}/emails.json"))
bodies = json.load(open(f"{args.out}/bodies.json"))

from ai_roles import CORE, RELATED, NONFT, fulltime_ai_segments  # noqa: E402
MARKER = re.compile(r"\((?:[mwfdxn*]{1,3}\s*/\s*){1,3}[mwfdxn*]\)|\((?:all|alle) gender\w*\)|\([mwfdxn]\s*/\s*[mwfdxn](?:\s*/\s*[mwfdxn])?(?:\s*\*)?\)", re.I)
PREAMBLE_END = ["Job Matches:", "matched the following jobs at", "passenden Stellen gefunden", "(Click to modify))", "Click to modify)", "Zu Deiner Stellenbenachrichtigung"]
TAIL = re.compile(r"(Remember to forward|Getting these notifications|Stellenbenachrichtigungen verwalten|Abonnement stornieren|Connect with us|To ensure delivery)", re.I)


def strip_preamble(text):
    cut = 0
    for m in PREAMBLE_END:
        i = text.rfind(m)
        if i != -1 and i < len(text) * 0.7:
            cut = max(cut, i + len(m))
    text = text[cut:]
    t = TAIL.search(text)
    return text[:t.start()] if t else text


def titles(text, rx):
    out = []
    marks = [m.end() for m in MARKER.finditer(text)]
    for m in rx.finditer(text):
        prev = max([e for e in marks if e <= m.start()] or [0])
        nxt = min([e for e in marks if e >= m.end()] or [len(text)])
        seg = text[max(prev, m.start() - 110):min(nxt + 1, m.end() + 90)]
        seg = re.sub(r"\s+", " ", seg).strip(" -–|,")
        # drop the trailing "- City, ST, DE" noise of the next title that bled in
        out.append(seg[:170])
    return out


cutoff = time.time() - args.recent_days * 86400
ai_by_id = {}
found = collections.defaultdict(dict)   # company -> title -> [first_seen, last_seen]
nletters = recent = 0
for e in emails:
    try:
        when = parsedate_to_datetime(e["date"]).timestamp()
    except Exception:
        continue
    nletters += 1
    ai_by_id[e["id"]] = fulltime_ai_segments(strip_preamble(bodies.get(e["id"], "")), MARKER)
    if when < cutoff:
        continue
    recent += 1
    body = strip_preamble(bodies.get(e["id"], ""))
    company = re.sub(r"\s+", " ", re.sub(r"^(Neue (von|bei|Stellenangebote von)|New jobs posted from|\w[\w ]* Jobs.*)", "", e["subject"]).strip()) or e["frm"].split("<")[0]
    company = company.replace("eingetragene Jobs", "").replace("veröffentlichte Stellen", "").strip() or e["frm"].split("@")[0]
    for t in set(titles(body, CORE)) | (set(titles(body, RELATED)) if args.also_related else set()):
        rec = found[company].setdefault(t, [when, when])
        rec[0], rec[1] = min(rec[0], when), max(rec[1], when)

day = lambda ts: time.strftime("%d %b %Y", time.localtime(ts))
print(f"{nletters} letters downloaded, {recent} from the last {args.recent_days} days.\n")
n = 0
for company, ts in sorted(found.items()):
    print(f"== {company} ==")
    for t, (a, b) in sorted(ts.items(), key=lambda kv: -kv[1][1]):
        print(f"   {t}   [{day(a)}" + (f" – {day(b)}" if day(a) != day(b) else "") + "]")
        n += 1
print(f"\n{n} AI-related role mentions in {len(found)} companies.")
if args.trash or args.trash_no_ai:
    PROTECT = re.compile(r"(your|deine|ihre|ihrer|deiner) (bewerbung|application)|application (was )?(sent|received)|bewerbung (eingegangen|erhalten)|interview|einladung|engeren auswahl|zusage|absage|rejection", re.I)
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    root = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
    creds = Credentials.from_authorized_user_file(os.path.join(root, ".gmail-token.json"))
    if not creds.valid:
        creds.refresh(Request())
    svc = build("gmail", "v1", credentials=creds)
    kept_ai = [e for e in emails if args.trash_no_ai and ai_by_id.get(e["id"])]
    if kept_ai:
        print("\n== LETTERS WITH A FULL-TIME AI ROLE (kept in the inbox) ==")
        for e in kept_ai:
            print(f"   {e['id']}  {e['date'][:16]}  {e['frm'].split('<')[0].strip()} | {e['subject'][:70]}")
            for t in ai_by_id[e["id"]][:6]:
                print(f"        - {t}")
    keep_ids = {e["id"] for e in kept_ai}
    todo = [e for e in emails if not PROTECT.search(e["subject"]) and e["id"] not in keep_ids]
    skipped = len(emails) - len(todo)
    log_dir = os.path.join(root, "data", "trashed_emails_log"); os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, time.strftime("%Y%m%d-%H%M%S") + "-companyletters.json")
    json.dump({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "messages": [dict(id=e["id"], subject=e["subject"], frm=e["frm"],
              removed_labels=[l for l in e.get("labels", []) if l in ("INBOX", "UNREAD")]) for e in todo]}, open(log_path, "w"), ensure_ascii=False, indent=1)
    for k in range(0, len(todo), 500):
        svc.users().messages().batchModify(userId="me", body={"ids": [e["id"] for e in todo[k:k + 500]], "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}).execute()
    print(f"\ntrashed {len(todo)} company letters ({skipped} protected or kept). undo log: {log_path}")
    args.commit = True
if args.commit:
    commit(TASK, started, pending=[])
    print("saved run time for next run:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)))
