"""Re-scrape jobs whose stored description is missing or too short and (with --apply) fill it in.

    .venv/bin/python scripts/rescrape_descriptions.py                  # dry run: list candidates, scrape, show result
    .venv/bin/python scripts/rescrape_descriptions.py --ids job-a job-b --apply

Candidates: every job whose description is under MIN_DESCRIPTION_CHARS (default statuses: all but rejected/archived).
Only `description` is written, plus title/company/location when they are blank. Back up first
(scripts/backup_db.py); nothing is written without --apply. A job description is non-negotiable: whatever
cannot be recovered is listed at the end so it can be fixed by hand (paste, Firecrawl, employer page).
"""
import argparse
import asyncio
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import job_extract  # noqa: E402

DB = os.path.join(ROOT, "jobtracker.db")


def candidates(ids, statuses):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("select id, title, company, location, status, url, description from jobs").fetchall()
    con.close()
    out = []
    for id_, title, company, location, status, url, desc in rows:
        if ids and id_ not in ids:
            continue
        if not ids and (status not in statuses or len((desc or "").strip()) >= job_extract.MIN_DESCRIPTION_CHARS):
            continue
        if not (url or "").startswith("http"):
            continue   # manual:/csv-import: rows have no page to scrape
        out.append(dict(id=id_, title=title, company=company, location=location, status=status,
                        url=url.split("#re-")[0], description=desc or ""))
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--statuses", nargs="*", default=["new", "applied", "interviewing", "offer"])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    jobs = candidates(set(args.ids), set(args.statuses))
    print(f"{len(jobs)} job(s) to re-scrape")
    if not jobs:
        return
    import main as app   # lazy: pulls in the MCP server module and Crawl4AI

    fixed, failed = [], []
    con = sqlite3.connect(DB) if args.apply else None
    try:
        for job in jobs:
            try:
                data = await app._scrape_job(job["url"])
            except Exception as e:   # robots.txt, timeouts, template pages
                failed.append((job, f"{type(e).__name__}: {str(e)[-220:]}"))
                continue
            desc = (data.get("description") or "").strip()
            problems = job_extract.description_problems(desc, job["url"])
            hard = [p for p in problems if "MISSING" in p or "TOO SHORT" in p or "loader" in p or "cookie banner" in p]
            print(f"{job['id']} {job['company'][:28]:28} {len(desc):6} chars  {'; '.join(problems) or 'ok'}")
            if hard or len(desc) < 600 or len(desc) <= len(job["description"]):
                failed.append((job, "; ".join(hard) or ("under 600 chars: not the full posting" if len(desc) < 600 else "nothing longer than what is stored")))
                continue
            if args.apply:
                fields = {"description": desc}
                for key in ("title", "company", "location"):
                    if not (job[key] or "").strip() and data.get(key):
                        fields[key] = data[key]
                sets = ", ".join(f"{k}=?" for k in fields)
                con.execute(f"update jobs set {sets} where id=?", (*fields.values(), job["id"]))
                con.commit()
            fixed.append(job["id"])
    finally:
        if con:
            con.close()
        if getattr(app, "_crawler", None):
            await app._crawler.close()

    print(f"\n{'written' if args.apply else 'would write'}: {len(fixed)}  {fixed}")
    if failed:
        print(f"STILL WITHOUT A USABLE DESCRIPTION: {len(failed)}")
        for job, why in failed:
            print(f"  {job['id']} {job['company']} | {job['title']} | {job['status']} | {job['url'][:80]} | {why}")
    if not args.apply:
        print("dry run -- add --apply to write")


asyncio.run(main())
