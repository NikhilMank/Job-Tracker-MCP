#!/usr/bin/env python3
"""Log the jobs the user applied to today (the daily file workflow in the `daily-job-routine` skill), without the MCP client.

Why a script: the running MCP server may be older than main.py (new tools such as add_job_from_text only appear after Claude Code
restarts). This calls the very same tool functions from main.py in-process, so duplicate protection, URL validation, robots.txt
check and field normalisation are identical.

  .venv/bin/python scripts/backup_db.py                                   # ALWAYS first
  .venv/bin/python scripts/log_todays_jobs.py links  [--file data/todays_jobs.md] [--report out.json]
  .venv/bin/python scripts/log_todays_jobs.py texts  SPEC.json            [--report out.json]
  .venv/bin/python scripts/log_todays_jobs.py clear  REPORT.json [REPORT2.json ...]   # verify ids exist, reset todays_jobs.md

links : every URL line under "## Links to add" (optional #tags after the URL): add_job (scrape), then status 'applied'.
        Already tracked <1 day ago = accidental double paste -> skipped; older = re-application -> allow_duplicate=True. Scrape failures
        (e.g. robots.txt 403 on stepstone/linkedin) are reported, never invented.
texts : SPEC.json = [{"title","description","company","location","salary","url","notes","tags"}, ...] -> add_job_from_text(status='applied').
        Only fill fields the pasted text states. Strip page chrome / recruiter names first (see the daily-job-routine skill).
clear : checks that every job id in the report(s) is in the database, then rewrites data/todays_jobs.md as the empty template
        (everything under the template headings removed, incl. any Done list).
"""
import argparse, asyncio, json, os, re, sqlite3, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DEFAULT_FILE = os.path.join(ROOT, "data", "todays_jobs.md")


def parse_links(path):
    text = open(path, encoding="utf-8").read()
    start = text.index("## Links to add")
    end = text.index("## Pasted descriptions") if "## Pasted descriptions" in text else len(text)
    out = []
    for line in text[start:end].splitlines():
        m = re.match(r"^\s*(https?://\S+)(.*)$", line)
        if m:
            out.append((m.group(1), re.findall(r"#([\w-]+)", m.group(2))))
    return out


def age_ok_to_skip(existing):
    return existing and (time.time() - int(existing["scraped_at"])) < 86400


async def run_links(args):
    import main
    from fastmcp.exceptions import ToolError
    report = []
    for url, tags in parse_links(args.file):
        rec = dict(url=url)
        try:
            try:
                res = await main.add_job(url=url, tags=tags or None)
            except ToolError as e:
                msg = str(e)
                if "Already tracked" in msg:
                    existing = await main._find_existing(url)
                    if age_ok_to_skip(existing):
                        rec.update(result="skipped (double paste, tracked <1 day ago)", id=existing["id"]); report.append(rec); print(rec, flush=True); continue
                    res = await main.add_job(url=url, tags=tags or None, allow_duplicate=True)
                    rec["re_application"] = True
                else:
                    raise
            sc = res.structured_content
            await main.update_job(id=sc["id"], status="applied")
            rec.update(result="added", id=sc["id"], title=sc.get("title"), company=sc.get("company"))
        except Exception as e:  # robots.txt, timeouts, blocked pages ...
            rec.update(result="FAILED", error=f"{type(e).__name__}: {str(e)[:200]}")
        report.append(rec); print(rec, flush=True)
    if args.report:
        json.dump(report, open(args.report, "w"), ensure_ascii=False, indent=1)


async def run_texts(args):
    import main
    from fastmcp.exceptions import ToolError
    report = []
    for spec in json.load(open(args.spec, encoding="utf-8")):
        rec = dict(title=spec["title"], company=spec.get("company"))
        kw = dict(title=spec["title"], description=spec["description"], company=spec.get("company"), location=spec.get("location"),
                  salary=spec.get("salary"), url=spec.get("url"), status="applied", tags=spec.get("tags"))
        try:
            try:
                res = await main.add_job_from_text(**kw)
            except ToolError as e:
                if "Already tracked" not in str(e):
                    raise
                url = spec.get("url")
                existing = await main._find_existing(url) if url else None
                if existing and age_ok_to_skip(existing):
                    rec.update(result="skipped (double paste, tracked <1 day ago)"); report.append(rec); print(rec, flush=True); continue
                res = await main.add_job_from_text(**kw, allow_duplicate=True)
                rec["re_application"] = True
            sc = res.structured_content
            if spec.get("notes"):
                await main.update_job(id=sc["id"], notes=spec["notes"])
            rec.update(result="added", id=sc["id"])
        except Exception as e:
            rec.update(result="FAILED", error=f"{type(e).__name__}: {str(e)[:200]}")
        report.append(rec); print(rec, flush=True)
    if args.report:
        json.dump(report, open(args.report, "w"), ensure_ascii=False, indent=1)


def clear(args):
    ids = [r["id"] for p in args.reports for r in json.load(open(p)) if r.get("id")]
    db = sqlite3.connect(os.path.join(ROOT, "jobtracker.db"))
    have = {r[0] for r in db.execute("select id from jobs where id in (%s)" % ",".join("?" * len(ids)), ids)} if ids else set()
    missing = [i for i in ids if i not in have]
    if missing:
        sys.exit(f"NOT clearing: {len(missing)} logged ids are missing from the database: {missing}")
    text = open(args.file, encoding="utf-8").read()
    head = text[:text.index("## Links to add")]
    template = (head + "## Links to add\n\nPaste one job URL per line. Optional tags after the URL, like `#python #remote`.\n\n"
                "<!-- stepstone.de and linkedin.com links are blocked by robots.txt: paste the job description under \"Pasted descriptions\" instead of the link. -->\n\n\n"
                "## Pasted descriptions\n\nFor Easy Apply jobs and sites that block scraping. One block per job, ended by a line with `---`.\n"
                "First line is `### Job title`; put `Company - address` on the next line, and the posting URL after it if you have it.\n\n"
                "<!-- paste descriptions here -->\n")
    open(args.file, "w", encoding="utf-8").write(template)
    print(f"checked {len(ids)} ids in the database; {os.path.relpath(args.file, ROOT)} reset to the empty template")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["links", "texts", "clear"])
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--report")
    ap.add_argument("reports", nargs="*")
    a, rest = ap.parse_known_args()
    if a.cmd == "links":
        asyncio.run(run_links(a))
    elif a.cmd == "texts":
        asyncio.run(run_texts(a))
    else:
        a.reports = ([a.spec] if a.spec else []) + a.reports + rest
        clear(a)
