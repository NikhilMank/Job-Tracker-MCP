#!/usr/bin/env python3
"""Move job-SUGGESTION mail from job platforms to the Trash (dry run unless --apply). Never deletes permanently.

Platforms (LinkedIn, Stepstone, Glassdoor, XING, jobvector, Instaffo, Indeed alerts) also send mail that MATTERS:
application receipts and status updates, "shortlisted" notices, recruiter messages, connection requests. So nothing is
deleted by sender alone: a message is trashed only if (sender rule matches) AND (it is a suggestion by subject, or the
sender only ever sends alerts) AND (no protect pattern matches). Everything platform-sent that is NOT trashed is listed
with its category so the user can decide (e.g. LinkedIn group digests, XING "Kennst Du ...?").

  .venv/bin/python clean_job_suggestions.py --out <scratchpad>/sugg --since all            # first sweep: whole mailbox
  .venv/bin/python clean_job_suggestions.py --out <scratchpad>/sugg                        # later runs: only mail newer than last run
  ... --apply                                                                              # trash + undo log + save the run time
Undo: .venv/bin/python clean_job_suggestions.py --undo data/trashed_emails_log/<file>.json
State (data/job_mail_state.json, task "job_suggestions"): only mail newer than the last completed run is read next time.
"""
import argparse, collections, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mail_state import since_query, commit  # noqa: E402
from ai_roles import fulltime_ai_segments  # noqa: E402
MARKER = re.compile(r"\((?:[mwfdxn*]{1,3}\s*/\s*){1,3}[mwfdxn*]\)|\((?:all|alle) gender\w*\)", re.I)

TASK = "job_suggestions"
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

# (rule name, sender regex, subject regex of suggestions or None = every mail from that sender is a suggestion)
RULES = [
    ("linkedin job alerts", r"jobalerts-noreply@linkedin\.com", None),
    ("linkedin job suggestions", r"jobs-noreply@linkedin\.com",
     r"looking for a new job\?|new jobs? (for|match|that)|jobs? (similar|you may|picked|recommended)|top job picks|recommended for you|jobs you might|"
     r"\bis hiring\b|^\w+, apply (now )?to|skills are in demand|prepare for your job search|update your profile to prepare|\bat [A-Z0-9]"),
    ("stepstone suggestions", r"@(jobagent|email|mail)\.stepstone\.de",
     r"new job opportunities|profile stands out|our recommendation|looking for candidates|neue (jobs|stellen)|passende (jobs|stellen)|job-?(agent|alert|empfehlung)|stellenangebote|empfehlung|chance for|in-demand job|skills are needed|closing soon|save time when job hunting|your progress, your next step|new job matches"),
    ("glassdoor", r"@glassdoor\.com", None),
    ("xing job suggestions", r"@(mail|e-mail)\.xing\.com",
     r"stellenangebot|job-?vorschl|wochencheck f.r die job-suche|passende (jobs|stellen)|suchen nach|spannende firmen"),
    ("jobvector", r"@jobagent\.jobvector\.de", None),
    ("instaffo suggestions", r"@app\.instaffo\.com",
     r"welcher passt besser|n.chster karriereschritt|jobs warten|wo du willst|schau mal, was wir haben|passende (jobs|stellen)|mehr bewerbungen, mehr chancen|job-pr.ferenzen|top-match|neuer job:|k.nnte gut zu dir passen|starte deine neue rolle|wartet auf dich|verpasse deine chance"),
    ("efinancialcareers", r"@efinancialcareers\.", None),
    ("workwise", r"@workwise\.io", r"neue jobs|jobs gefunden|passende|jobs passen|passen zu deinem profil"),
    ("talent rocket", r"Talent Rocket|talentrocket", None),
    ("linkedin network job posts", r"messages-noreply@linkedin\.com", r"(are|is) hiring|open to work|hired near"),
    ("talent newsletters", r"careeralerts\.|JobLead|eFinancialCareers", None),
    ("indeed job alerts", r"@(alert|jobalert|jm|www)?\.?indeed\.com", r"new jobs?|neue (jobs|stellen)|jobs? f.r dich|job ?alert|empfohlene|n.chsten job"),
]
# Mail that must never be trashed, whatever the sender says: it concerns the user's own applications / contacts.
PROTECT = re.compile(
    r"(your|deine|deiner|ihre|ihrer|dein) (bewerbung|application)|application (was )?sent|bewerbung (.ber indeed|bei )|"
    r"engeren auswahl|shortlist|interview(?! for this job)|einladung|invitation|nachricht von|message from|inmail|application updates?|"
    r"complete your application|zugangsdaten|passwort|password|security (alert|code)|sicherheits(code|warnung|hinweis)|account security|\brechnung|invoice|billing", re.I)
# "Your application was viewed by X" tells the user nothing until the company answers; trash it. A reply or a message from the
# company ("message from", "nachricht", "responded") is never matched here and stays protected.
VIEWED = re.compile(r"(application (was )?viewed|viewed your application|bewerbung wurde (angesehen|angeschaut|gesehen|ge.ffnet)|hat (sich )?(deine|ihre) bewerbung (angesehen|angeschaut))", re.I)
VIEWED_SENDERS = re.compile(r"(@|\.)(linkedin|stepstone|indeed|xing|glassdoor|jobvector|instaffo)\.", re.I)
ANSWER = re.compile(r"message|nachricht|respond|repl(y|ied)|antwort|interview|einladung|invitation|update", re.I)
NEVER_SENDERS = re.compile(r"(messages-noreply|invitations|inmail-hit-reply|security-noreply|billing-noreply)@linkedin\.com", re.I)

ap = argparse.ArgumentParser()
ap.add_argument("--out", help="working dir for the download")
ap.add_argument("--since", default="auto", help="auto (since last run) | all | N (days)")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--undo")
ap.add_argument("--max", type=int, default=3000)
ap.add_argument("--no-fetch", action="store_true")
ap.add_argument("--report-ai", action="store_true", help="read the bodies and list the full-time AI roles seen in suggestions before they are trashed (use only if the user wants roles listed)")
ap.add_argument("--hold-ai", action="store_true", help="read the mail bodies and do NOT trash suggestions that list a full-time AI role; list them in the report instead (daily-job-routine skill)")
args = ap.parse_args()

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
creds = Credentials.from_authorized_user_file(os.path.join(ROOT, ".gmail-token.json"))
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds)

if args.undo:
    log = json.load(open(args.undo))
    groups = collections.defaultdict(list)
    for m in log["messages"]:
        groups[tuple(sorted(m["removed_labels"]))].append(m["id"])
    for removed, ids in groups.items():
        for k in range(0, len(ids), 500):
            svc.users().messages().batchModify(userId="me", body={"ids": ids[k:k + 500], "addLabelIds": list(removed), "removeLabelIds": ["TRASH"]}).execute()
        print(f"restored {len(ids)} messages from the Trash (labels back: {list(removed)})")
    sys.exit(0)

if not args.out:
    sys.exit("--out is required")
senders = "(from:linkedin.com OR from:stepstone.de OR from:glassdoor.com OR from:indeed.com OR from:xing.com OR from:jobvector.de OR from:instaffo.com OR from:efinancialcareers.de OR from:workwise.io OR from:alignerr.com OR from:hiring.amazon OR from:deere OR from:growthhub.telekom.com OR from:talentrocket OR from:airswift)"
since, started = since_query(TASK, default_days=60, mode=args.since)
if args.no_fetch:
    # With --no-fetch the mail was read earlier: the watermark must be the time that download STARTED, never "now".
    started = int(os.path.getmtime(os.path.join(args.out, "emails.json"))) - 7200  # conservative: 2 h before the last write
LABEL_Q = os.environ.get("JOBTRACKER_LABEL_PREFIX", "JobApplications").lower()
query = f"{senders} -in:sent -in:trash -label:{LABEL_Q} -label:{LABEL_Q}-rejected {since}".strip()
if not args.no_fetch:
    subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "jobtracker-gmail-sync", "scripts", "fetch_gmail_label.py"),
                    "--query", query] + ([] if (args.hold_ai or args.report_ai) else ["--no-bodies"]) + ["--body-chars", "6000", "--max", str(args.max), "--out", args.out], check=True, stdout=subprocess.DEVNULL)
emails = json.load(open(f"{args.out}/emails.json"))
bodies = json.load(open(f"{args.out}/bodies.json")) if (args.hold_ai or args.report_ai) and os.path.exists(f"{args.out}/bodies.json") else {}

trash, keep, held, seen_ai = collections.defaultdict(list), collections.defaultdict(list), [], []
for e in emails:
    frm, subj = e["frm"], e["subject"]
    network_job_post = re.search(r"messages-noreply@linkedin\.com", frm, re.I) and re.search(r"(are|is) hiring|open to work|hired near", subj, re.I)
    if VIEWED.search(subj) and VIEWED_SENDERS.search(frm) and not ANSWER.search(subj):
        trash["application viewed notice"].append(e)
        continue
    if (NEVER_SENDERS.search(frm) and not network_job_post) or PROTECT.search(subj):
        keep["protected: " + (re.search(r"<([^>]+)>", frm).group(1) if "<" in frm else frm)[:40]].append(e)
        continue
    for name, sender_rx, subj_rx in RULES:
        if re.search(sender_rx, frm, re.I) and (subj_rx is None or re.search(subj_rx, subj, re.I)):
            segs = fulltime_ai_segments(subj + " . " + bodies.get(e["id"], e.get("snippet", "")), MARKER) if (args.hold_ai or args.report_ai) else []
            if segs and args.hold_ai:
                held.append((e, segs))
            else:
                if segs:
                    seen_ai.append((e, segs))
                trash[name].append(e)
            break
    else:
        keep["not a job suggestion: " + (re.search(r"<([^>]+)>", frm).group(1) if "<" in frm else frm)[:40]].append(e)

total = sum(len(v) for v in trash.values())
print(f"\n== WOULD TRASH: {total} ==")
for name, v in sorted(trash.items(), key=lambda kv: -len(kv[1])):
    print(f"  {len(v):4}  {name}")
print(f"\n== KEPT (platform mail that is not a plain job suggestion): {sum(len(v) for v in keep.values())} ==")
for name, v in sorted(keep.items(), key=lambda kv: -len(kv[1])):
    print(f"  {len(v):4}  {name}  e.g. {v[0]['subject'][:60]}")
if seen_ai:
    print(f"\n== FULL-TIME AI ROLES SEEN IN {len(seen_ai)} SUGGESTIONS (these are trashed) ==")
    for e, segs in seen_ai:
        print(f"   {e['id']}  {e['date'][:16]}  {e['frm'].split('<')[0].strip()} | {e['subject'][:70]}")
        for t in segs[:5]:
            print(f"        - {t}")
if held:
    print(f"\n== HELD BACK: {len(held)} suggestions that list a full-time AI role (kept in the inbox) ==")
    for e, segs in held:
        print(f"   {e['id']}  {e['date'][:16]}  {e['frm'].split('<')[0].strip()} | {e['subject'][:70]}")
        for t in segs[:5]:
            print(f"        - {t}")
json.dump({k: [e["id"] for e in v] for k, v in trash.items()}, open(f"{args.out}/to_trash.json", "w"))

if args.apply and total:
    ids = [e["id"] for v in trash.values() for e in v]
    manifest = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "messages": []}
    for k in range(0, len(ids), 500):
        chunk = ids[k:k + 500]
        for e in [x for v in trash.values() for x in v if x["id"] in set(chunk)]:
            manifest["messages"].append(dict(id=e["id"], subject=e["subject"], frm=e["frm"],
                                             removed_labels=[l for l in e.get("labels", []) if l in ("INBOX", "UNREAD")]))
    log_dir = os.path.join(ROOT, "data", "trashed_emails_log"); os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, time.strftime("%Y%m%d-%H%M%S") + ".json")
    json.dump(manifest, open(log_path, "w"), ensure_ascii=False, indent=1)
    for k in range(0, len(ids), 500):
        svc.users().messages().batchModify(userId="me", body={"ids": ids[k:k + 500], "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]}).execute()
    commit(TASK, started, pending=[])
    print(f"\ntrashed {len(ids)} messages (recoverable from Trash for ~30 days). undo log: {log_path}\nsaved run time for next run: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}")
elif not args.apply:
    print("\ndry run -- re-run with --apply to move these to the Trash (nothing saved, nothing changed)")
