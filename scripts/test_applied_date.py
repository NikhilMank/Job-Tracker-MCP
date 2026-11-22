"""Plain-script test: main.py stamps 'Applied: M/D/YYYY' into notes when a job first becomes 'applied'.

Uses a throw-away database (never jobtracker.db). Exits 1 on failure. Run from the project root:
    .venv/bin/python scripts/test_applied_date.py
"""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

# pure helper
check("empty notes", main._with_applied_date(None).startswith("Applied: "), True)
check("existing line kept", main._with_applied_date("x\nApplied: 1/2/2025"), "x\nApplied: 1/2/2025")
check("appended on new line", main._with_applied_date("call HR").startswith("call HR\nApplied: "), True)

async def run():
    main.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")
    base = {"title": "T", "company": "C", "location": "L", "description": "d" * 300, "scraped_at": 1700000000}
    for jid, status, notes in (("a", "new", None), ("b", "new", "keep me"), ("c", "applied", None), ("d", "new", "Applied: 3/4/2025")):
        await main._insert_job({**base, "id": jid, "url": f"https://x.example/{jid}", "status": status, "notes": notes})
    g = main._get_job_by_id
    check("insert as new: no stamp", (await g("a"))["notes"], None)
    check("insert as applied: stamped", (await g("c"))["notes"].startswith("Applied: "), True)
    await main.update_job(id="a", status="applied")
    check("update to applied: stamped", (await g("a"))["notes"].startswith("Applied: "), True)
    await main.update_job(id="b", status="applied")
    n = (await g("b"))["notes"]
    check("existing notes preserved + stamped", (n.startswith("keep me\nApplied: "), n.count("Applied:")), (True, 1))
    await main.update_job(id="d", status="applied")
    check("existing Applied line untouched", (await g("d"))["notes"], "Applied: 3/4/2025")
    before = (await g("a"))["notes"]
    await main.update_job(id="a", status="interviewing")
    await main.update_job(id="a", status="applied")
    check("re-applying does not add a second line", (await g("a"))["notes"], before)
    await main.update_job(id="a", notes="replaced")
    check("explicit notes still replace", (await g("a"))["notes"], "replaced")

asyncio.run(run())
print("\n".join(fails) or "all passed")
sys.exit(1 if fails else 0)
