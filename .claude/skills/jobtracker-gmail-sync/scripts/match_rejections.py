#!/usr/bin/env python3
"""Match rejection emails to tracker jobs using company AND job-title evidence.

Input : emails.json + bodies.json from fetch_gmail_label.py (a label of rejection emails)
Output: decisions.json  (one record per email: class, evidence level, best job, candidates)

Evidence levels (strongest first), per (email, job):
  A  exact job title in the email AND company name in sender/subject/first 1500 chars
     (generic titles like "AI Engineer" additionally need the company in sender/subject)
  B  >=60% of the title's distinctive words in the email AND company in head
     (needs company in sender/subject unless the title has >=3 distinctive words)
  C  company name in sender/subject and the company has exactly ONE job in the tracker
  D  company in head only -> ambiguous, never auto-applied

Classes: UPDATE / UPDATE-company  -> safe to mark rejected (still needs rejection wording,
                                     not user-sent, email not older than the application)
         explained-rejected       -> the email belongs to a job that is already rejected
         skip-predates            -> email is older than the application date
         review*                  -> ambiguous; list for the user, do not change
         nomatch                  -> no company in the tracker (e.g. pre-dates the tracker)

Usage:
  .venv/bin/python match_rejections.py --db jobtracker.db --emails work/emails.json \
      --bodies work/bodies.json --out work/decisions.json [--tag csv-import] [--user-hint yourname]
"""
import argparse, collections, json, math, os, re, sqlite3, sys, unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="jobtracker.db")
ap.add_argument("--emails", required=True)
ap.add_argument("--bodies", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--tag", default="", help="only consider jobs whose tags contain this (default: ALL jobs, incl. ones added later via add_job)")
ap.add_argument("--user-hint", action="append", default=[h.strip().lower() for h in os.environ.get("JOBTRACKER_USER_HINTS", "").split(",") if h.strip()],
                help="substrings of the user's own addresses; their mails are never evidence")
args = ap.parse_args()


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


SUFFIX = set("gmbh ag se inc ltd llc co kg mbh corp corporation limited plc sa bv nv group gruppe holding "
             "deutschland germany the und ug sas kgaa cie europe e v".split())
GENERIC = set("team inform automation new open quality hrworks data software digital tech technology solutions "
              "consulting services systems international global ai careers career jobs talent recruiting personal "
              "bewerbung hochschule universitat university technische institut applied machine learning cloud "
              "platform engineering research".split())
# Company strings that are not real company names / are ordinary words -> never match on them.
BAD_KEYS = set("nicht erwahnt right search profile system systems future first european german platform digital "
               "source sourc alpha computer experience verein discover hallo welt".split()) | {"nicht erwahnt", "right search", "ai system", "hallo welt"}
TITLE_STOP = set("m w d f x all genders gender mwd fmd fmx wmx and for the in of mit und fur im der die das an bei als "
                 "to a at or ein eine senior junior engineer developer entwickler specialist manager expert consultant "
                 "remote hybrid vollzeit teilzeit".split())
# Sentence-level rejection classifier shared with the gmail-file-rejections skill (keyword lists such as
# "leider"/"sorry" caused false positives; a rejection needs a full decision sentence).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gmail-file-rejections", "scripts"))
from rejection_classifier import classify  # noqa: E402

emails = json.load(open(args.emails))
bodies = json.load(open(args.bodies))
db = sqlite3.connect(args.db)
rows = (db.execute("select id,title,company,status,notes,url,substr(description,1,6000),scraped_at from jobs where tags like ?", (f"%{args.tag}%",)).fetchall() if args.tag
        else db.execute("select id,title,company,status,notes,url,substr(description,1,6000),scraped_at from jobs").fetchall())


def applied_date(notes):
    m = re.search(r"Applied: (\d+)/(\d+)/(\d+)", notes or "")
    return datetime(int(m[3]), int(m[1]), int(m[2])) if m else None


def company_keys(company):
    acr = {a.lower() for a in re.findall(r"\(([A-Za-z]{3,8})\)", company or "")}   # "European Molecular Biology Laboratory (EMBL)" -> embl
    words = [x for x in norm(company).split() if x not in SUFFIX]
    core = [x for x in words if x not in GENERIC]
    keys = set()
    full = " ".join(words)
    if len(full) >= 4 and full not in GENERIC:
        keys.add(full)
    if core and len(core[0]) >= 5:
        keys.add(core[0])
    if len(core) >= 2:
        keys.add(" ".join(core[:2]))
    return {k for k in keys | acr if k not in BAD_KEYS}


df, jobs = collections.Counter(), {}
for jid, title, company, status, notes, url, desc, scraped_at in rows:
    toks = {t for t in norm(title).split() if t not in TITLE_STOP and len(t) > 2}
    df.update(toks)
    jobs[jid] = dict(id=jid, title=title, company=company, status=status, toks=toks, nt=norm(title),
                     keys=company_keys(company), applied=applied_date(notes) or (datetime.utcfromtimestamp(scraped_at) if scraped_at else None),   # no "Applied:" line (add_job) -> date added to the tracker
                     reftext=norm(" ".join(x or "" for x in (title, url, desc, notes))))
weight = lambda t: 1 / math.log(2.5 + df[t])
key_index = collections.defaultdict(list)
jobs_per_company = collections.Counter()
for j in jobs.values():
    jobs_per_company[norm(j["company"])] += 1
    for k in j["keys"]:
        key_index[k].append(j["id"])

decisions = []
for e in emails:
    body = bodies.get(e["id"], "")
    hdr = " " + norm(e["frm"] + " " + e["subject"]) + " "
    head = " " + norm(e["frm"] + " " + e["subject"] + " " + body[:1500]) + " "
    full = " " + norm(e["frm"] + " " + e["subject"] + " " + body) + " "
    words = set(full.split())
    try:
        sent = parsedate_to_datetime(e["date"]).replace(tzinfo=None)
    except Exception:
        sent = None
    from_user = any(h in e["frm"].lower() for h in args.user_hint)
    has_rejection_wording = classify(e["frm"], e["subject"], body)["verdict"] == "REJECTION"

    evidence = []
    for jid in {i for k, ids in key_index.items() if f" {k} " in head for i in ids}:
        j = jobs[jid]
        in_hdr = any(f" {k} " in hdr for k in j["keys"])
        in_head = any(f" {k} " in head for k in j["keys"])
        exact = len(j["nt"]) >= 8 and f" {j['nt']} " in full
        total = sum(weight(t) for t in j["toks"]) or 1
        overlap = sum(weight(t) for t in j["toks"] if t in words) / total if j["toks"] else 0
        predates = bool(sent and j["applied"] and (sent - j["applied"]).days < -1)
        generic_title = len(j["toks"]) <= 2
        # job/ad numbers quoted in the email ("1085/2026", "E362/B", "JR3800") that also occur in the job's own text
        refs = {norm(t) for t in re.findall(r"\b(?=[A-Za-z0-9/_-]*\d)[A-Za-z0-9][A-Za-z0-9/_-]{4,}\b", e["subject"] + " " + body[:2500])
                if not re.fullmatch(r"20\d\d|\d{1,2}[./]\d{1,2}[./]\d{2,4}", t)}
        ref_hit = any(len(r) >= 4 and f" {r} " in f" {j['reftext']} " for r in refs)
        if in_head and ref_hit:
            level = "A"
        elif in_head and exact and (in_hdr or not generic_title):
            level = "A"
        elif in_head and overlap >= 0.6 and (in_hdr or len(j["toks"]) >= 3):
            level = "B"
        elif in_hdr and jobs_per_company[norm(j["company"])] == 1 and len(norm(j["company"])) >= 5:
            level = "C"
        elif in_head:
            level = "D"
        else:
            continue
        evidence.append((level, round(overlap, 2), predates, jid))
    if not evidence:
        decisions.append(dict(id=e["id"], cls="nomatch"))
        continue

    level = next(l for l in "ABCD" if any(x[0] == l for x in evidence))
    pool = sorted((x for x in evidence if x[0] == level), key=lambda x: (x[2], -x[1]))
    best = pool[0]
    tied = [x for x in pool if x[1] == best[1] and x[2] == best[2]]
    job = jobs[best[3]]
    open_tied = [x for x in tied if jobs[x[3]]["status"] != "rejected" and not x[2]]
    if level in "AB" and len(tied) > 1 and len({jobs[x[3]]["nt"] for x in tied}) == 1:
        # identical role listed several times (re-applications / spelling variants of the company) = ONE candidacy: all rows get the outcome
        cls = "UPDATE" if open_tied else ("explained-rejected" if all(jobs[x[3]]["status"] == "rejected" for x in tied) else "skip-predates")
        decisions.append(dict(id=e["id"], cls=cls if not (cls == "UPDATE" and (from_user or not has_rejection_wording)) else "review-" + ("user-sent" if from_user else "no-rejection-wording"),
                              lvl=level, job=best[3], jobs=[x[3] for x in open_tied], overlap=best[1], cands=[x[3] for x in pool[:5]]))
        continue
    if level in "AB" and len(tied) == 1:
        cls = "explained-rejected" if job["status"] == "rejected" else ("skip-predates" if best[2] else "UPDATE")
    elif level == "C":
        cls = "explained-rejected" if job["status"] == "rejected" else ("skip-predates" if best[2] else "UPDATE-company")
    else:
        open_jobs = [x for x in pool if jobs[x[3]]["status"] != "rejected" and not x[2]]
        cls = "review" if open_jobs else "explained-rejected"
    if cls.startswith("UPDATE") and (from_user or not has_rejection_wording):
        cls = "review-" + ("user-sent" if from_user else "no-rejection-wording")
    decisions.append(dict(id=e["id"], cls=cls, lvl=level, job=best[3], overlap=best[1],
                          cands=[x[3] for x in pool[:5]]))

json.dump(decisions, open(args.out, "w"))
print(collections.Counter((d["cls"], d.get("lvl")) for d in decisions))
