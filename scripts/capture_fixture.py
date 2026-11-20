"""Crawl one job URL exactly like main._scrape_job pass 1 and store it as an offline fixture.

    .venv/bin/python scripts/capture_fixture.py NAME URL [--apply]

Dry run prints what would be stored; --apply writes scripts/fixtures/job_pages.json
(keys: url, meta, markdown, jsonld, css), which scripts/test_job_extract.py replays.
"""
import argparse
import asyncio
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIXTURES = os.path.join(ROOT, "scripts", "fixtures", "job_pages.json")


async def capture(url: str) -> dict:
    import main
    from crawl4ai import CacheMode, CrawlerRunConfig, JsonCssExtractionStrategy

    await main.validate_url(url)
    crawler = await main._ensure_crawler()
    try:
        res = await crawler.arun(url, config=CrawlerRunConfig(
            check_robots_txt=True, word_count_threshold=5, max_retries=1, verbose=False, exclude_all_images=True,
            cache_mode=CacheMode.BYPASS, extraction_strategy=JsonCssExtractionStrategy(main.JOB_SCHEMA)))
        if not res.success:
            sys.exit(f"crawl failed: {res.error_message}")
        css = res.extracted_content
        css = json.loads(css) if isinstance(css, str) and css else (css or [])
        md = (res.markdown.raw_markdown or "") if res.markdown else ""
        ld = re.findall(r'<script[^>]+application/ld\+json[^>]*>.*?</script>', res.html or "", re.S | re.I)
        return {"url": url, "meta": res.metadata or {}, "markdown": md, "jsonld": ld, "css": css}
    finally:
        await crawler.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("url")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    page = asyncio.run(capture(args.url))
    print(f"{args.name}: markdown {len(page['markdown'])} chars, {len(page['jsonld'])} JSON-LD blocks, {len(page['meta'])} meta keys")
    if args.apply:
        pages = json.load(open(FIXTURES))
        pages[args.name] = page
        json.dump(pages, open(FIXTURES, "w"), ensure_ascii=False, indent=1)
        print(f"stored in {FIXTURES}")
    else:
        print("dry run -- add --apply to store")
