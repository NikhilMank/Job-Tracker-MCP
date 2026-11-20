"""
Personal Job Tracker MCP server powered by Crawl4AI.

Scrapes job postings, extracts structured data, and stores them locally.
Provides tools to track, search, and manage your job applications.
"""

import asyncio
import hashlib
import json
import os
import re
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

import aiosqlite
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "jobtracker.db")
CACHE_DIR = os.path.join(PROJECT_ROOT, ".crawl4ai-cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_MAX_CHARS = 20_000
MAX_MAX_CHARS = 100_000

BLOCKED_IP_RANGES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "0.0.0.0/8",
    "224.0.0.0/4",
]

# ---------------------------------------------------------------------------
# CSS Extraction Schema for Job Postings
# ---------------------------------------------------------------------------

JOB_SCHEMA = {
    "baseSelector": "main, article, .job-description, .description, [data-testid='job-description']",
    "fields": [
        {
            "name": "title",
            "selector": "h1, h2.job-title, [data-testid='job-title'], .job-title",
            "type": "text",
        },
        {
            "name": "company",
            "selector": ".company, .employer, [data-testid='company-name'], .employer-name",
            "type": "text",
        },
        {
            "name": "location",
            "selector": ".location, .job-location, [data-testid='job-location'], .work-location",
            "type": "text",
        },
        {
            "name": "salary",
            "selector": ".salary, .compensation, [data-testid='salary'], .pay",
            "type": "text",
        },
        {
            "name": "description",
            "selector": ".description, .job-description, [data-testid='job-description'], .content",
            "type": "html",
        },
        {
            "name": "requirements",
            "selector": ".requirements, .qualifications, [data-testid='requirements'], .job-requirements",
            "type": "html",
        },
        {
            "name": "benefits",
            "selector": ".benefits, .perks, [data-testid='benefits'], .job-benefits",
            "type": "html",
        },
    ],
}

# Valid statuses
VALID_STATUSES = {"new", "applied", "interviewing", "offer", "rejected", "archived"}


# ---------------------------------------------------------------------------
# SSRF Protection
# ---------------------------------------------------------------------------

async def validate_url(url: str) -> str:
    """Validate a URL and reject schemes/private IPs."""
    from urllib.parse import urlparse

    if not isinstance(url, str) or not url.strip():
        raise ToolError("Invalid URL: URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ToolError(f"Invalid URL '{url}': only http:// and https:// are allowed.")

    host = parsed.hostname
    if host is None:
        raise ToolError(f"Invalid URL '{url}': hostname is missing.")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ToolError(f"Invalid URL '{url}': localhost is blocked.")

    try:
        resolved = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or 443)
        import ipaddress
        for info in resolved:
            ip = info[4][0]
            for cidr in BLOCKED_IP_RANGES:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(cidr):
                    raise ToolError(
                        f"Invalid URL '{url}': host '{host}' resolves to a blocked IP range."
                    )
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Could not resolve host '{host}': {type(e).__name__}: {e}") from e

    return url.strip()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_db_initialized = False


@asynccontextmanager
async def db():
    """Open a connection to the SQLite database."""
    global _db_initialized
    if not _db_initialized:
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                salary_currency TEXT,
                description TEXT,
                requirements TEXT,
                benefits TEXT,
                job_type TEXT,
                experience_level TEXT,
                remote_type TEXT,
                posted_date INTEGER,
                scraped_at INTEGER NOT NULL,
                status TEXT DEFAULT 'new',
                notes TEXT,
                tags TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)"
        )
        await conn.commit()
        _db_initialized = True
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    yield conn
    await conn.close()


async def _insert_job(job: dict) -> None:
    """Insert a new job into the database."""
    async with db() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (
                id, url, title, company, location,
                salary_min, salary_max, salary_currency,
                description, requirements, benefits,
                job_type, experience_level, remote_type,
                posted_date, scraped_at, status, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("id"),
                job.get("url"),
                job.get("title"),
                job.get("company"),
                job.get("location"),
                job.get("salary_min"),
                job.get("salary_max"),
                job.get("salary_currency"),
                job.get("description"),
                job.get("requirements"),
                job.get("benefits"),
                job.get("job_type"),
                job.get("experience_level"),
                job.get("remote_type"),
                job.get("posted_date"),
                job.get("scraped_at"),
                job.get("status", "new"),
                job.get("notes"),
                job.get("tags"),
            ),
        )
        await conn.commit()


async def _get_job_by_id(job_id: str) -> dict | None:
    """Fetch a job by ID."""
    async with db() as conn:
        cursor = await conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def _get_all_jobs(
    status: str | None = None,
    company: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Fetch jobs with optional filters."""
    async with db() as conn:
        query = "SELECT * FROM jobs WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        query += " ORDER BY scraped_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def _update_job_in_db(
    job_id: str,
    status: str | None = None,
    notes: str | None = None,
    tags: str | None = None,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    salary: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update job fields."""
    async with db() as conn:
        fields = []
        params = []
        if status is not None:
            fields.append("status=?")
            params.append(status)
        for column, value in (("title", title), ("company", company), ("location", location)):
            if value is not None:
                fields.append(f"{column}=?")
                params.append(value.strip())
        if salary is not None:
            salary_min, salary_max, salary_currency = _parse_salary(salary)
            fields.append("salary_min=?, salary_max=?, salary_currency=?")
            params.extend([salary_min, salary_max, salary_currency])
        if description is not None:
            fields.append("description=?")
            params.append(description.strip())
        if notes is not None:
            fields.append("notes=?")
            params.append(notes)
        if tags is not None:
            fields.append("tags=?")
            params.append(tags)
        if not fields:
            return None
        params.append(job_id)
        await conn.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id=?",
            params,
        )
        await conn.commit()
        return await _get_job_by_id(job_id)


async def _delete_job_from_db(job_id: str) -> bool:
    """Delete a job from the database."""
    async with db() as conn:
        await conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        await conn.commit()
        return True


async def _search_jobs(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across job fields."""
    async with db() as conn:
        sql = """
            SELECT * FROM jobs
            WHERE title LIKE ? OR company LIKE ?
               OR description LIKE ? OR requirements LIKE ?
               OR location LIKE ?
            ORDER BY scraped_at DESC LIMIT ?
        """
        params = [f"%{query}%"] * 5 + [limit]
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def _get_stats() -> dict:
    """Get dashboard statistics."""
    async with db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM jobs")
        total = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status"
        )
        by_status = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await conn.execute(
            "SELECT company, COUNT(*) FROM jobs GROUP BY company ORDER BY COUNT(*) DESC LIMIT 10"
        )
        by_company = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE scraped_at > ?",
            (int(datetime.now(timezone.utc).timestamp()) - 7 * 86400,),
        )
        recent_count = (await cursor.fetchone())[0]

        return {
            "total": total,
            "by_status": by_status,
            "by_company": by_company,
            "recent_count": recent_count,
        }


# ---------------------------------------------------------------------------
# Crawl4AI helpers
# ---------------------------------------------------------------------------

_crawler = None
_crawler_lock = asyncio.Lock()
# 18 parallel add_job calls (the daily link batch) overloaded one browser and one of them hit the tool timeout: scrape at most 4 at a time
_scrape_sem = asyncio.Semaphore(4)


async def _ensure_crawler():
    """Lazily initialize the AsyncWebCrawler on first use."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    global _crawler
    async with _crawler_lock:
        if _crawler is None:
            browser_conf = BrowserConfig(
                headless=True,
                text_mode=True,
                light_mode=True,
                viewport_width=1080,
                viewport_height=600,
                user_agent="JobTracker-MCP/0.1 (personal use)",
            )
            _crawler = AsyncWebCrawler(
                config=browser_conf,
                base_directory=CACHE_DIR,
                thread_safe=True,
            )
            await _crawler.start()
    return _crawler


async def _scrape_job(url: str) -> dict:
    """Scrape a job posting URL and extract structured data."""
    from crawl4ai import (
        CacheMode,
        CrawlerRunConfig,
        JsonCssExtractionStrategy,
    )

    global _crawler
    if _crawler is None:
        _crawler = await _ensure_crawler()

    from job_extract import description_problems, is_shell as job_extract_is_shell, merge_job_fields, needs_render_retry, pick_css_hit

    def _conf(**kw):
        return CrawlerRunConfig(
            check_robots_txt=True,
            word_count_threshold=5,
            max_retries=1,
            verbose=False,
            exclude_all_images=True,
            remove_consent_popups=True,    # some sites store the cookie dialog as the description
            **kw,
        )

    def _markdown(res) -> str:
        return (res.markdown.raw_markdown or res.markdown.fit_markdown or "") if res.markdown else ""

    def _css(res) -> dict:
        extracted = res.extracted_content
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except json.JSONDecodeError:
                return {}
        return pick_css_hit(extracted)

    # Pass 1: fast static fetch with CSS extraction. Always fresh: a cached copy can predate edits to the posting
    # (Siemens changed its location between fetches) or lack the JSON-LD block, and add_job is not a hot path.
    result = await _crawler.arun(
        url,
        config=_conf(cache_mode=CacheMode.BYPASS, extraction_strategy=JsonCssExtractionStrategy(JOB_SCHEMA)),
    )
    # Workday / Oracle HCM / Ashby serve an empty script shell; Crawl4AI's anti-bot check reports that as a failed
    # crawl ("script_heavy_shell, 0 chars visible"). That is a JS page, not a block: go on to the render-wait pass.
    js_shell = (not result.success and "robots.txt" not in (result.error_message or "")
                and bool(re.search(r"script_heavy_shell|minimal_text|no_content_elements", result.error_message or "")))
    if not result.success and not js_shell:
        raise ToolError(f"Failed to scrape {url}: HTTP {result.status_code} - {result.error_message}")
    if js_shell:
        css, data, via = {}, merge_job_fields({}, {}, "", None, url), "markdown_fallback"
    else:
        css = _css(result)
        data = merge_job_fields(css, result.metadata, _markdown(result), result.html, url)
        via = "css_extraction" if css.get("title") else "markdown_fallback"

    # Pass 2: JS-rendered pages (Workday, Ashby, ...) come back empty; wait for the render
    # and re-read metadata + markdown. Quality gate: blank title or tiny description.
    if needs_render_retry(data):
        rendered = await _crawler.arun(
            url,
            config=_conf(
                cache_mode=CacheMode.BYPASS,
                wait_until="networkidle",
                delay_before_return_html=4,
                page_timeout=40000,
                extraction_strategy=JsonCssExtractionStrategy(JOB_SCHEMA),
            ),
        )
        if not rendered.success and js_shell:
            raise ToolError(f"Failed to scrape {url}: HTTP {rendered.status_code} - {rendered.error_message}")
        if rendered.success:
            data2 = merge_job_fields(_css(rendered) or css, rendered.metadata, _markdown(rendered), rendered.html, url)
            # keep anything pass 1 found that pass 2 lacks, including a longer description (the render pass can
            # come back with just the contact box of a page whose posting pass 1 already had)
            for key, value in data.items():
                if key not in ("warnings", "company_source") and not data2.get(key) and value:
                    data2[key] = value
            if len(data.get("description") or "") > 1.5 * len(data2.get("description") or "") and not job_extract_is_shell(data.get("description")) \
                    and not description_problems(data.get("description"), url):
                data2["description"] = data["description"]
                data2["warnings"] = [w for w in data2.get("warnings", []) if not w.startswith("description")]
            data, via = data2, "rendered"

    if data.pop("nav_only", False):
        raise ToolError(
            f"{url} serves only site navigation (job list or JS app) and no posting text, even after a render wait. "
            "Nothing was stored. Find the posting text (employer page, then Firecrawl / an aggregator copy) and use "
            "add_job_from_text with this URL; log it in data/scraper_failures.md."
        )
    data.pop("nav_only", None)
    if data.pop("placeholder_only", False):
        raise ToolError(
            f"{url} is a template page with placeholder (Lorem Ipsum) text and no real posting. "
            "Ask the user to paste the description and use add_job_from_text."
        )
    data["extracted_via"] = via
    return data


def _parse_salary(salary_text: str | None) -> tuple[int | None, int | None, str | None]:
    """Parse salary text into min, max, currency."""
    if not salary_text:
        return None, None, None

    import re
    salary_text = salary_text.lower().strip()

    # Detect currency
    currency = None
    if "$" in salary_text or "usd" in salary_text:
        currency = "USD"
    elif "€" in salary_text or "eur" in salary_text:
        currency = "EUR"
    elif "£" in salary_text or "gbp" in salary_text:
        currency = "GBP"
    elif "kr" in salary_text or "sek" in salary_text or "nok" in salary_text:
        currency = "SEK"

    # Extract numbers (salary ranges)
    values = []
    for n in re.findall(r"\d[\d.,]*", salary_text):
        n = n.rstrip(".,")
        if "." in n and "," in n:
            # the last separator is the decimal mark: 3.500,50 (EU) or 3,500.50 (US)
            decimal = "," if n.rfind(",") > n.rfind(".") else "."
            thousands = "." if decimal == "," else ","
            n = n.replace(thousands, "").replace(decimal, ".")
        elif "," in n:
            # 60,000 / 1,200,000 are thousands groups; 3500,50 is a decimal comma
            n = n.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", n) else n.replace(",", ".")
        elif "." in n:
            # 60.000 is a thousands group (EU); 60.5 is a decimal
            n = n.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", n) else n
        try:
            values.append(int(float(n)))
        except ValueError:
            continue
    if not values:
        return None, None, currency

    if len(values) >= 2:
        return min(values), max(values), currency
    elif len(values) == 1:
        return values[0], None, currency

    return None, None, currency


def _normalize_job_data(raw: dict, url: str) -> dict:
    """Normalize extracted job data into the database schema."""
    title = raw.get("title", "")
    company = raw.get("company", "")
    location = raw.get("location", "")
    salary_text = raw.get("salary", "")
    description = raw.get("description", "")
    requirements = raw.get("requirements", "")
    benefits = raw.get("benefits", "")

    salary_min, salary_max, salary_currency = _parse_salary(salary_text)

    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "description": description,
        "requirements": requirements,
        "benefits": benefits,
        "job_type": None,
        "experience_level": None,
        "remote_type": None,
        "posted_date": None,
        "scraped_at": int(datetime.now(timezone.utc).timestamp()),
        "status": "new",
        "notes": None,
        "tags": None,
    }


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def _age_text(scraped_at: int) -> str:
    secs = max(0, int(datetime.now(timezone.utc).timestamp()) - int(scraped_at))
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} days ago"


async def _find_existing(url: str) -> dict | None:
    """Most recent job stored under this URL, including earlier re-applications (url#re-...)."""
    escaped = url.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    async with db() as conn:
        cursor = await conn.execute(
            "SELECT id, title, company, status, scraped_at FROM jobs "
            "WHERE url=? OR url LIKE ? ESCAPE '\\' ORDER BY scraped_at DESC LIMIT 1",
            (url, escaped + "#re-%"),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


def _duplicate_error(existing: dict) -> ToolError:
    return ToolError(
        f"Already tracked as {existing['id']}: {existing['title'] or 'Untitled'} at "
        f"{existing['company'] or 'Unknown'} (status={existing['status']}, added "
        f"{_age_text(existing['scraped_at'])}). Pass allow_duplicate=true to add it again "
        "as a re-application."
    )


def _reapply_url(url: str) -> str:
    """Unique-but-equivalent URL for a re-application; servers ignore the #fragment."""
    return f"{url}#re-{datetime.now(timezone.utc):%Y-%m-%d}-{uuid.uuid4().hex[:4]}"


mcp = FastMCP("JobTracker", mask_error_details=True)


# ---------------------------------------------------------------------------
# Tool: add_job
# ---------------------------------------------------------------------------

@mcp.tool(
    name="add_job",
    description="""
Scrape a job posting URL and store the extracted data in your local job database.

This tool uses Crawl4AI to extract structured data (title, company, location, salary, description, requirements, benefits) from job posting pages.
It works with Indeed, Greenhouse, Lever and most company career pages, and falls back to markdown extraction for unknown sites.
stepstone.de and linkedin.com are blocked by robots.txt (HTTP 403) and will fail: do NOT retry them with another scraper; ask the user to paste the description and use add_job_from_text.
The reply states the description length; a line starting '!! DESCRIPTION PROBLEM' means the stored job description is missing, short, still has page chrome, or comes from an aggregator: tell the user and fix it in the same run. A job description is non-negotiable.
Always try this tool first for every job posting URL. Firecrawl/WebFetch are only a fallback after this tool fails or returns blank fields, and every fallback must be logged in data/scraper_failures.md (see CLAUDE.md).

Parameters:
- url: The absolute http(s) URL of the job posting
- tags: Optional list of tags to categorize the job (e.g., ['react', 'remote', 'senior'])
- allow_duplicate: If the URL is already tracked the call fails (before scraping) and reports the existing job. Set true to add it again as a re-application (stored as url#re-<date>-<id>)
""",
    annotations={"readOnlyHint": False, "openWorldHint": True},
    timeout=240.0,   # includes time queued behind the scrape semaphore
)
async def add_job(
    url: Annotated[str, "Absolute http(s) URL of the job posting"],
    tags: Annotated[list[str] | None, "Optional tags for the job"] = None,
    allow_duplicate: Annotated[bool, "Add again even if this URL is already tracked"] = False,
    ctx: Context = None,
) -> ToolResult:
    """Scrape a job posting and store it in the tracker."""
    url = await validate_url(url)
    existing = await _find_existing(url)
    if existing and not allow_duplicate:
        raise _duplicate_error(existing)
    if ctx is not None:
        await ctx.info(f"Scraping job posting: {url}")

    try:
        async with _scrape_sem:
            raw = await _scrape_job(url)
        job = _normalize_job_data(raw, _reapply_url(url) if existing else url)
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        job["id"] = job_id
        job["tags"] = json.dumps(tags) if tags else None

        await _insert_job(job)

        # extraction problems the caller must report and log in data/scraper_failures.md. A job description is
        # non-negotiable: description problems lead the reply and set description_ok=false.
        warnings = raw.get("warnings") or []
        desc_problems = [w for w in warnings if w.lower().startswith("description")]
        other = [w for w in warnings if w not in desc_problems]
        desc_len = len((job["description"] or "").strip())
        head = f"Added job: {job['title'] or 'Untitled'} at {job['company'] or 'Unknown'} ({job_id}), description {desc_len} chars"
        alert = (f"\n!! DESCRIPTION PROBLEM, TELL THE USER AND FIX IT NOW: {'; '.join(desc_problems)}" if desc_problems else "")
        note = f" [check: {'; '.join(other)}]" if other else ""
        return ToolResult(
            content=[{"type": "text", "text": head + note + alert}],
            structured_content={
                "id": job_id,
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "status": "new",
                "description_chars": desc_len,
                "description_ok": not desc_problems,
                "warnings": warnings,
                "message": f"Job added successfully. ID: {job_id}" + (" -- BUT THE DESCRIPTION HAS PROBLEMS" if desc_problems else ""),
            },
        )
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to add job: {type(e).__name__}: {e}") from e


# ---------------------------------------------------------------------------
# Tool: add_job_from_text
# ---------------------------------------------------------------------------

@mcp.tool(
    name="add_job_from_text",
    description="""
Store a job from text you already have (e.g. a description pasted from an Easy Apply page) without scraping anything.

Parameters:
- title: Job title (required)
- description: Full job description text (required)
- company, location, salary, requirements, benefits: Only what the text actually states; leave out anything not given
- url: Link to the posting if known. If omitted, a stable 'manual:<hash>' key is generated, so pasting the same job twice is rejected as a duplicate
- status: new, applied, interviewing, offer, rejected, archived (default 'new')
- tags: Optional list of tags
- allow_duplicate: If the same URL/text is already tracked the call fails and reports the existing job. Set true to add it again as a re-application
The reply states the description length and flags '!! DESCRIPTION PROBLEM' (too short, pasted page chrome): tell the user.
""",
    annotations={"readOnlyHint": False, "openWorldHint": False},
)
async def add_job_from_text(
    title: Annotated[str, "Job title"],
    description: Annotated[str, "Full job description text"],
    company: Annotated[str | None, "Company name"] = None,
    location: Annotated[str | None, "Job location"] = None,
    salary: Annotated[str | None, "Salary text as written in the posting"] = None,
    requirements: Annotated[str | None, "Requirements section, if separate"] = None,
    benefits: Annotated[str | None, "Benefits section, if separate"] = None,
    url: Annotated[str | None, "Posting URL if known (not fetched)"] = None,
    status: Annotated[str, "Initial job status"] = "new",
    tags: Annotated[list[str] | None, "Optional tags for the job"] = None,
    allow_duplicate: Annotated[bool, "Add again even if this URL/text is already tracked"] = False,
) -> ToolResult:
    """Store a job from supplied text; no network access."""
    if status not in VALID_STATUSES:
        raise ToolError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if not title.strip() or not description.strip():
        raise ToolError("title and description must be non-empty.")

    if url and url.strip():
        from urllib.parse import urlparse

        url = url.strip()
        if urlparse(url).scheme not in ("http", "https"):
            raise ToolError(f"Invalid URL '{url}': only http:// and https:// are allowed.")
    else:
        key = f"{(company or '').strip().lower()}|{title.strip().lower()}|{description.strip()}"
        url = f"manual:{hashlib.sha1(key.encode()).hexdigest()[:12]}"

    existing = await _find_existing(url)
    if existing and not allow_duplicate:
        raise _duplicate_error(existing)
    stored_url = _reapply_url(url) if existing else url

    try:
        job = _normalize_job_data(
            {
                "title": title.strip(),
                "company": (company or "").strip(),
                "location": (location or "").strip(),
                "salary": (salary or "").strip(),
                "description": description.strip(),
                "requirements": (requirements or "").strip(),
                "benefits": (benefits or "").strip(),
            },
            stored_url,
        )
        job["id"] = f"job-{uuid.uuid4().hex[:8]}"
        job["status"] = status
        job["tags"] = json.dumps(tags) if tags else None
        await _insert_job(job)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to add job: {type(e).__name__}: {e}") from e

    from job_extract import description_problems

    desc_problems = description_problems(job["description"], pasted=True)
    desc_len = len(job["description"].strip())
    alert = (f"\n!! DESCRIPTION PROBLEM, TELL THE USER AND FIX IT NOW: {'; '.join(desc_problems)}" if desc_problems else "")
    return ToolResult(
        content=[{"type": "text", "text": f"Added job: {job['title']} at {job['company'] or 'Unknown'} ({job['id']}, status={status}), description {desc_len} chars{alert}"}],
        structured_content={
            "id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "status": status,
            "url": stored_url,
            "re_application": existing is not None,
            "description_chars": desc_len,
            "description_ok": not desc_problems,
            "warnings": desc_problems,
            "message": f"Job added successfully. ID: {job['id']}" + (" -- BUT THE DESCRIPTION HAS PROBLEMS" if desc_problems else ""),
        },
    )


# ---------------------------------------------------------------------------
# Tool: list_jobs
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_jobs",
    description="""
List tracked jobs with optional filters.

Parameters:
- status: Filter by status (new, applied, interviewing, offer, rejected, archived)
- company: Filter by company name (partial match)
- limit: Maximum jobs to return (default 50, max 200)
- offset: Pagination offset (default 0)
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def list_jobs(
    status: Annotated[str | None, "Filter by job status"] = None,
    company: Annotated[str | None, "Filter by company name"] = None,
    limit: Annotated[int, "Maximum jobs to return"] = 50,
    offset: Annotated[int, "Pagination offset"] = 0,
    ctx: Context = None,
) -> ToolResult:
    """List tracked jobs with optional filters."""
    if status and status not in VALID_STATUSES:
        raise ToolError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if not 1 <= limit <= 200:
        raise ToolError("limit must be between 1 and 200.")

    jobs = await _get_all_jobs(status=status, company=company, limit=limit, offset=offset)

    return ToolResult(
        content=[{"type": "text", "text": f"Found {len(jobs)} jobs"}],
        structured_content={
            "count": len(jobs),
            "jobs": [
                {
                    "id": j["id"],
                    "title": j["title"],
                    "company": j["company"],
                    "location": j["location"],
                    "status": j["status"],
                    "scraped_at": j["scraped_at"],
                    "tags": j["tags"],
                }
                for j in jobs
            ],
        },
    )


# ---------------------------------------------------------------------------
# Tool: get_job
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_job",
    description="""
Get full details of a specific job by ID.

Parameters:
- id: The job ID (returned by add_job or list_jobs)
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=10.0,
)
async def get_job(
    id: Annotated[str, "The job ID"],
    ctx: Context = None,
) -> ToolResult:
    """Get full job details by ID."""
    job = await _get_job_by_id(id)
    if job is None:
        raise ToolError(f"Job '{id}' not found.")

    return ToolResult(
        content=[{"type": "text", "text": f"Job: {job['title']} at {job['company']}"}],
        structured_content=job,
    )


# ---------------------------------------------------------------------------
# Tool: update_job
# ---------------------------------------------------------------------------

@mcp.tool(
    name="update_job",
    description="""
Update a job's status, notes, tags, or details that scraping missed.

Parameters:
- id: The job ID
- status: New status (new, applied, interviewing, offer, rejected, archived)
- notes: Add notes about the job
- tags: Update tags (list of strings)
- title, company, location: Correct fields the scraper left blank (only what the posting states)
- salary: Salary text as written in the posting; parsed into min/max/currency
- description: Replace the stored description (e.g. when the scrape left it empty); full posting text only
""",
    annotations={"readOnlyHint": False, "openWorldHint": False},
    timeout=10.0,
)
async def update_job(
    id: Annotated[str, "The job ID"],
    status: Annotated[str | None, "New job status"] = None,
    notes: Annotated[str | None, "Notes about the job"] = None,
    tags: Annotated[list[str] | None, "Update tags"] = None,
    title: Annotated[str | None, "Job title"] = None,
    company: Annotated[str | None, "Company name"] = None,
    location: Annotated[str | None, "Job location"] = None,
    salary: Annotated[str | None, "Salary text as written in the posting"] = None,
    description: Annotated[str | None, "Replacement description text"] = None,
    ctx: Context = None,
) -> ToolResult:
    """Update a job's status, notes, tags, or details."""
    if status and status not in VALID_STATUSES:
        raise ToolError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if title is not None and not title.strip():
        raise ToolError("title must not be empty.")

    job = await _update_job_in_db(
        id,
        status=status,
        notes=notes,
        tags=json.dumps(tags) if tags else None,
        title=title,
        company=company,
        location=location,
        salary=salary,
        description=description,
    )
    if job is None:
        raise ToolError(f"Job '{id}' not found or no changes provided.")

    return ToolResult(
        content=[{"type": "text", "text": f"Updated job {id}"}],
        structured_content={
            "id": id,
            "status": job["status"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "salary_min": job["salary_min"],
            "salary_max": job["salary_max"],
            "salary_currency": job["salary_currency"],
            "notes": job["notes"],
            "tags": job["tags"],
        },
    )


# ---------------------------------------------------------------------------
# Tool: delete_job
# ---------------------------------------------------------------------------

@mcp.tool(
    name="delete_job",
    description="""
Delete a job from the tracker.

Parameters:
- id: The job ID to delete
""",
    annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    timeout=10.0,
)
async def delete_job(
    id: Annotated[str, "The job ID to delete"],
    ctx: Context = None,
) -> ToolResult:
    """Delete a job from the tracker."""
    job = await _get_job_by_id(id)
    if job is None:
        raise ToolError(f"Job '{id}' not found.")

    await _delete_job_from_db(id)
    return ToolResult(
        content=[{"type": "text", "text": f"Deleted job {id}"}],
        structured_content={"success": True, "id": id},
    )


# ---------------------------------------------------------------------------
# Tool: search_jobs
# ---------------------------------------------------------------------------

@mcp.tool(
    name="search_jobs",
    description="""
Search tracked jobs by keyword across title, company, description, and requirements.

Parameters:
- query: Search keyword(s)
- limit: Maximum results (default 20, max 100)
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def search_jobs(
    query: Annotated[str, "Search keyword(s)"],
    limit: Annotated[int, "Maximum results"] = 20,
    ctx: Context = None,
) -> ToolResult:
    """Search jobs by keyword."""
    if not query.strip():
        raise ToolError("Search query must not be empty.")
    if not 1 <= limit <= 100:
        raise ToolError("limit must be between 1 and 100.")

    jobs = await _search_jobs(query, limit=limit)

    return ToolResult(
        content=[{"type": "text", "text": f"Found {len(jobs)} matching jobs for '{query}'"}],
        structured_content={
            "query": query,
            "count": len(jobs),
            "jobs": [
                {
                    "id": j["id"],
                    "title": j["title"],
                    "company": j["company"],
                    "location": j["location"],
                    "status": j["status"],
                    "scraped_at": j["scraped_at"],
                }
                for j in jobs
            ],
        },
    )


# ---------------------------------------------------------------------------
# Tool: get_stats
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_stats",
    description="""
Get dashboard statistics about your tracked jobs.

Returns total count, breakdown by status, top companies, and recent activity.
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=10.0,
)
async def get_stats(ctx: Context = None) -> ToolResult:
    """Get job tracking statistics."""
    stats = await _get_stats()

    return ToolResult(
        content=[{"type": "text", "text": f"Total jobs: {stats['total']}"}],
        structured_content=stats,
    )




if __name__ == "__main__":
    mcp.run()