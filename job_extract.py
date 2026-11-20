"""Pure helpers that turn a crawled page (metadata + markdown + CSS hits) into job fields.

No heavy imports here, so it is cheap to import and easy to test
(`.venv/bin/python scripts/test_job_extract.py`).
"""

import html as _html
import json
import re
from urllib.parse import urlparse

MIN_DESCRIPTION_CHARS = 200

_PLACEHOLDER_RE = re.compile(r"lorem ipsum|dolor sit amet", re.I)
# <title> values that name the site/page type, not the posting
_GENERIC_TITLES = {"jobs", "job", "careers", "career", "karriere", "stellenangebote", "loading", "home", "none", "detail", "details", "jobdetails", "jobportal", "job portal", "stellenangebot", "stellendetails", ""}
_GENDER_RE = re.compile(r"\(?\s*[mwfdgx]\s*[/|]\s*[mwfdgx]|\b(all genders|gn)\b", re.I)
_SEPARATORS = (" | ", " - ", " – ", " — ", " @ ", " at ")


# SPA shells that come back before the job content has rendered (ELO JobPortal, generic loaders)
_SHELL_RE = re.compile(r"loading data|lade daten|powered by elo|please enable javascript|bitte aktivieren sie javascript|\bnoscript\b", re.I)


def is_shell(markdown: str | None) -> bool:
    """Short page that is mostly a loader/error shell, not a posting."""
    md = markdown or ""
    return bool(_SHELL_RE.search(md)) and len(md) < 1500


def is_placeholder(text: str | None) -> bool:
    return bool(text) and bool(_PLACEHOLDER_RE.search(text)) and len(text) < 40


def strip_placeholder(text: str) -> str:
    """Drop paragraphs that are Lorem Ipsum filler (SuccessFactors preview pages)."""
    if not text or not _PLACEHOLDER_RE.search(text):
        return text
    blocks = re.split(r"\n\s*\n", text)
    return "\n\n".join(b for b in blocks if not _PLACEHOLDER_RE.search(b)).strip()


def _clean(value) -> str:
    """Decode HTML entities ('AI &amp; Co', '&nbsp;'), collapse whitespace, drop generic/placeholder values."""
    if value is None:
        return ""
    value = " ".join(_html.unescape(str(value)).replace("\xa0", " ").split())
    return "" if value.lower() in _GENERIC_TITLES or is_placeholder(value) else value


# career-site labels around a company name: "Jobs@Birds on Mars", "Karriere bei X", "X Karriere", "Jobs at X"
_CAREER_PREFIX = re.compile(r"^(?:jobs?|karriere|careers?|stellenangebote)\s*(?:@|bei|at|von|:|-|–|\|)\s*", re.I)
_CAREER_SUFFIX = re.compile(r"\s*[-–|:]?\s*(?:jobs?|karriere|careers?)$", re.I)
_DOMAIN_RE = re.compile(r"(?:www\.)?[\w-]+(?:\.[\w-]+)*\.(?:de|com|org|net|io|eu|co|uk|at|ch|ai|app)", re.I)
_LEGAL_FORMS = r"GmbH(?: & Co\.? ?KG)?|mbH|AG|SE|KG|UG(?: \(haftungsbeschränkt\))?|Ltd\.?|Inc\.?|B\.V\.|S\.A\.|S\.p\.A\."
_LEGAL_RE = re.compile(rf"\b(?:{_LEGAL_FORMS})$")


def _clean_company(value) -> str:
    """A company name as the employer would write it: no career-site label, no bare domain."""
    value = _clean(value)
    if not value or _DOMAIN_RE.fullmatch(value):
        return ""
    if all(label in _ATS_LABELS for label in re.split(r"[.\s]+", value.lower()) if label):   # 'onlyfy.jobs' is the platform
        return ""
    value = _CAREER_SUFFIX.sub("", _CAREER_PREFIX.sub("", value)).strip()
    return _strip_org_code(value)


def complete_legal_form(name: str, text: str) -> str:
    """'Birds on Mars' -> 'Birds on Mars GmbH' when the page itself writes the legal form right after the name."""
    if not name or _LEGAL_RE.search(name):
        return name
    m = re.search(rf"\b{re.escape(name)}\s+({_LEGAL_FORMS})(?![\w.])", text or "")
    return f"{name} {m.group(1)}" if m else name


# host labels that name the job platform / TLD, not the employer
_ATS_LABELS = {
    "www", "jobs", "job", "careers", "career", "karriere", "karrieren", "bewerbung", "apply", "hire", "recruiting", "stellen",
    "com", "de", "org", "net", "io", "eu", "co", "uk", "at", "ch", "ai", "app", "factorialhr", "personio", "ashbyhq", "greenhouse",
    "lever", "workday", "myworkdayjobs", "smartrecruiters", "recruitee", "join", "hrworks", "successfactors", "jobs2web",
    "rexx-systems", "onlyfy", "softgarden", "teamtailor", "bamboohr", "workable", "breezy", "jobvite", "icims", "taleo", "umantis",
    "d-vision", "heyjobs", "stepstone", "linkedin", "indeed", "xing", "glassdoor",
}


def company_from_host(url: str, text: str) -> str:
    """Employer from the career-site host ('tectakegmbh.factorialhr.de' -> 'tectake', 'careers.zurich.com' -> 'Zurich'),
    but only when the page text writes that name, so the page backs it."""
    for label in (urlparse(url or "").hostname or "").lower().split("."):
        if label in _ATS_LABELS or len(label) < 3:
            continue
        base = re.sub(r"^(?:karriere|jobs|careers)[-_]", "", label)
        base = re.sub(r"[-_]?(?:gmbh|ag|se|kg|group|gruppe)$", "", base)
        words = base.replace("-", " ").replace("_", " ").strip()
        if len(words) < 3:
            continue
        pattern = r"[-\s]".join(re.escape(w) for w in re.split(r"[-_\s]+", words) if w)
        m = re.search(rf"(?<![\w@/.-]){pattern}(?![\w@/.-])", text or "", re.I)
        if m:
            return complete_legal_form(m.group(0), text)
    return ""


_NOT_A_PLACE = re.compile(r"mail|^\W*(?:all|alle|vor ort|remote|hybrid|n/?a|none|null|tbd)\W*$|\*\s*$|^\d+$", re.I)


def _clean_location(value) -> str:
    """CSS text often glues the field label on: 'LocationDortmund' -> 'Dortmund'. Form labels / filter text that a
    selector picked up ('E-Mail*', 'All', 'Vor Ort') are not places: blank, so a better source can win."""
    value = _clean(value)
    value = re.sub(r"^(?:location|standort|einsatzort|ort|arbeitsort)\s*:?\s*(?=[A-ZÄÖÜ])", "", value, flags=re.I).strip()
    return "" if _NOT_A_PLACE.search(value) else value


def _strip_org_code(name: str) -> str:
    """Workday legal-entity codes: '1000 PATRIZIA SE' -> 'PATRIZIA SE', '922E Airbus ...' -> 'Airbus ...'."""
    return re.sub(r"^(?=[A-Z0-9]{3,5}\s)[A-Z0-9]*\d[A-Z0-9]*\s+(?=\D)", "", name)


def split_title_company(og_title: str, site_name: str = "") -> tuple[str, str]:
    """'Role - Company' / 'Role | Company' -> (role, company). Only splits when the tail
    matches og:site_name or the title has exactly two parts; otherwise returns (title, '')."""
    og_title = _clean(og_title)
    site_name = _clean(site_name)
    if not og_title:
        return "", site_name
    for sep in _SEPARATORS:
        if sep in og_title:
            head, _, tail = og_title.rpartition(sep)
            head, tail = head.strip(), tail.strip()
            if not head or not tail:
                continue
            if not _clean(head):          # "Jobs | groninger group": a site label, not the role
                return "", site_name or tail
            if site_name and tail.lower() == site_name.lower():
                return head, site_name
            if sep != " at " and head.count(sep) == 0 and len(tail.split()) <= 4 and not site_name \
                    and not _GENDER_RE.search(tail):
                # two-part "Role - Company": the page states it, but only trust short tails
                return head, tail
    return og_title, site_name


def _text(value) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value") or ""
    return " ".join(str(value or "").split())


def _jsonld_salary(base) -> str:
    """schema.org baseSalary -> '4800 - 5900 EUR per month' (parsed by main._parse_salary)."""
    if not isinstance(base, dict):
        return ""
    val = base.get("value")
    val = val if isinstance(val, dict) else {"value": val}
    lo, hi = val.get("minValue", val.get("value")), val.get("maxValue")
    try:
        nums = [str(int(float(n))) for n in (lo, hi) if n not in (None, "")]
    except (TypeError, ValueError):
        return ""
    if not nums:
        return ""
    unit = str(val.get("unitText") or "").lower()
    return f"{' - '.join(nums)} {base.get('currency') or ''}{' per ' + unit if unit else ''}".strip()


def fields_from_jsonld(page_html: str | None) -> dict:
    """schema.org JobPosting JSON-LD (most career sites embed it): title, company, location, text."""
    out: dict = {}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html or "", re.S | re.I):
        try:
            blob = json.loads(m.group(1).strip())
        except ValueError:
            continue
        nodes = blob if isinstance(blob, list) else blob.get("@graph", [blob]) if isinstance(blob, dict) else []
        for node in nodes:
            kind = node.get("@type") if isinstance(node, dict) else None
            if kind != "JobPosting" and not (isinstance(kind, list) and "JobPosting" in kind):
                continue
            loc = node.get("jobLocation")
            loc = loc[0] if isinstance(loc, list) and loc else loc
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            country = _text(addr.get("addressCountry")) if isinstance(addr, dict) else ""
            country = country.upper() if len(country) == 2 else country   # "de" -> "DE"
            place = ", ".join(p for p in (_text(addr.get("addressLocality")) or _text(addr.get("addressRegion")), country) if p) if isinstance(addr, dict) else ""
            salary = _jsonld_salary(node.get("baseSalary"))
            raw = _html.unescape(str(node.get("description") or ""))
            raw = re.sub(r"</(p|li|div|h\d|ul)>|<br\s*/?>", "\n", raw, flags=re.I)
            desc = "\n".join(" ".join(l.split()) for l in re.sub(r"<[^>]+>", " ", raw).splitlines() if l.strip())
            out = {
                "title": _clean(_html.unescape(_text(node.get("title")))),
                "company": _clean_company(_html.unescape(_text(node.get("hiringOrganization")))),
                "location": place,
                "description": desc,
                "salary": salary,
                "remote": "TELECOMMUTE" in json.dumps(node.get("jobLocationType") or ""),
            }
            return out
    return out


_COMPANY_LABELS = r"unternehmen|gesellschaft|arbeitgeber|company|employer|firma"
_LOCATION_LABELS = r"standorte?|einsatzort|arbeitsort|location|locations|ort"
_NOT_A_NAME = re.compile(r"\b(suchen|search|alle|all|filter|auswählen|select)\b", re.I)


def labelled_fields(markdown: str) -> dict:
    """'**Unternehmen:** Atos' / '**Gesellschaft:** Porsche Consulting GmbH' / '**Einsatzort:** Stuttgart' lines.
    These are the employer's own statement, so they beat the site footer / og:site_name."""
    out: dict = {}
    for key, labels in (("company", _COMPANY_LABELS), ("location", _LOCATION_LABELS)):
        m = re.search(rf"^[\s*_>#-]*\**(?:{labels})\**\s*:\s*\**\s*(.+?)\s*$", markdown or "", re.I | re.M)
        if m:
            value = " ".join(m.group(1).replace("*", " ").split())
            if 1 < len(value) <= 160 and not _NOT_A_NAME.search(value):
                out[key] = value
    return out


def heading_location(markdown: str) -> str:
    """City heading right above the H1 ('## Bamberg') or 'City, Country' line right under it."""
    md = markdown or ""
    h1 = re.search(r"^#\s+.+$", md, re.M)
    if not h1:
        return ""
    above = md[:h1.start()].rstrip().splitlines()[-1:] or [""]
    m = re.fullmatch(r"#{2,3}\s+([A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ\w][\wäöüß.\-]*){0,2})", above[0].strip())
    if m:
        return m.group(1)
    below = (md[h1.end():].strip().splitlines() or [""])[0].strip()
    if re.fullmatch(r"[A-ZÄÖÜ][\wäöüß.\- ]{1,30}(, [A-ZÄÖÜ][\wäöüß.\- ]{1,30}){1,2}", below):
        return below
    return ""


_FIELD_LABELS = {
    "location": r"locations?|standorte?|einsatzort|arbeitsort|ort",
    "salary": r"gehalt(?: pro (?:jahr|monat))?|salary|vergütung",
}


def _field_value(line: str) -> str:
    line = " ".join(_html.unescape(line).replace("\xa0", " ").split())
    return line if line and not re.search(r"https?:|[:\[\]()<>@]|^[*\-•#>]", line) else ""


def field_list(markdown: str) -> dict:
    """Label and value on their own lines, no colon (ATS field lists):
    'Ort\nKöln', 'Gehalt pro Jahr\n&#8364;74,000.00 EUR' -> one value line each;
    a bold '**Location**' (Avature) is followed by 'Spain / Barcelona / Barcelona' (country, region, city) -> 'Barcelona, Spain'."""
    out: dict = {}
    lines = (markdown or "").splitlines()
    for key, labels in _FIELD_LABELS.items():
        pattern = re.compile(rf"^\s*(\**)\s*(?:{labels})\s*\**\s*$", re.I)
        for i, line in enumerate(lines):
            m = pattern.match(line)
            if not m:
                continue
            take = 3 if m.group(1) and key == "location" else 1
            values: list[str] = []
            for nxt in lines[i + 1:i + 1 + take]:
                value = _field_value(nxt)
                if not value or len(value) > 60:
                    break
                if value not in values:
                    values.append(value)
            if key == "location":
                values = [v for v in values if v[:1].isupper() and not _NOT_A_PLACE.search(v)]
                if values:
                    out[key] = ", ".join(reversed(values))
            elif values and re.search(r"\d", values[0]):
                out[key] = values[0]
            if key in out:
                break
    return out


_COUNTRIES = r"Deutschland|Germany|Österreich|Austria|Schweiz|Switzerland|Luxemburg|Luxembourg"


def bullet_location(markdown: str) -> str:
    """Posting header bullets under the H1 ('* Unbefristet * Vollzeit * Höchberg, Bayern, Deutschland')."""
    md = markdown or ""
    h1 = re.search(r"^#\s+.+$", md, re.M)
    if not h1:
        return ""
    for line in md[h1.end():h1.end() + 600].splitlines():
        m = re.match(rf"^\s*(?:[*\-•]\s*)+([A-ZÄÖÜ][\wäöüßÄÖÜ.\- ]{{1,40}}(?:, [A-ZÄÖÜ][\wäöüßÄÖÜ.\- ]{{1,40}}){{1,3}})\s*$", line)
        if m and re.search(rf"(?:{_COUNTRIES})$", m.group(1).strip()):
            parts = [p.strip() for p in m.group(1).split(",")]
            return ", ".join(p for i, p in enumerate(parts) if i == 0 or p != parts[i - 1])   # 'Berlin, Berlin, Germany'

    return ""


def location_list(markdown: str) -> str:
    """Siemens fact block: 'Location(s)' on its own line, the place as the next bullet ('* Munich - - Germany')."""
    m = re.search(r"^\s*Location\(s\)\s*\n\s*[*\-•]\s*(.+?)\s*$", markdown or "", re.M)
    return re.sub(r"\s*(?:-\s*)+(?=\S)", ", ", m.group(1)).strip(" ,") if m else ""


def homeoffice_location(markdown: str) -> str:
    """Header line 'Köln mit Homeoffice' near the top of the posting -> 'Köln'."""
    for line in (markdown or "").splitlines()[:15]:
        m = re.fullmatch(r"\s*([A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ][\wäöüß.\-]*)?)\s+(?:mit|\+|/)\s*(?:Home-?office|Remote)\s*", line)
        if m:
            return m.group(1)
    return ""


def standort_phrase(text: str) -> str:
    """'AI Engineer (w/m/d) für den Standort Starnberg (Percha)' in the first lines of an og:description."""
    m = re.search(r"für den Standort ([A-ZÄÖÜ][\wäöüß\-]+(?: [A-ZÄÖÜ][\wäöüß\-]+)?(?: \([\wäöüß ]+\))?)", (text or "")[:400])
    return m.group(1) if m else ""


def job_id_cities(markdown: str) -> str:
    """Avature header: 'Job ID: 114023' followed by one bullet per city ('* Cologne', '* Munich') -> 'Cologne, Munich'."""
    lines = (markdown or "").splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*job id\s*:", line, re.I):
            cities = []
            for nxt in lines[i + 1:i + 14]:
                m = re.fullmatch(r"\s*[*\-•]\s*([A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ][\wäöüß.\-]*)?)\s*", nxt)
                if m:
                    cities.append(m.group(1))
                elif nxt.strip():
                    break
            return ", ".join(cities) if len(cities) >= 1 else ""
    return ""


_ICON_NAMES = {"location_on", "timer", "calendar_clock", "work", "arrow_back", "schedule", "place", "euro", "business", "apartment", "payments", "mail", "phone"}
_EMPLOYMENT_LINE = re.compile(r"^(?:apply(?: now| for this job)?|jetzt bewerben|full[- ]?time|part[- ]?time|vollzeit|teilzeit|permanent(?: employee)?|festanstellung|unbefristet|befristet|contract)\b", re.I)
_NOT_A_CITY = {"engineering", "product", "sales", "marketing", "design", "data", "operations", "finance", "legal", "remote", "hybrid", "onsite", "on-site", "apply", "technology", "research", "people", "hr", "it", "ai", "platform", "software"}


def icon_location(markdown: str) -> str:
    """Material-icon header (SSF, some Personio skins): 'location_on' on its own line, the place on the next."""
    lines = (markdown or "").splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip() == "location_on":
            value = _field_value(lines[i + 1])
            if value and len(value) <= 80 and value[:1].isupper() and not _NOT_A_PLACE.search(value):
                return value
    return ""


def postcode_location(markdown: str) -> str:
    """Address block under a Standort/Location heading: '74177 Bad Friedrichshall' -> 'Bad Friedrichshall'."""
    m = re.search(r"^[\s*>#-]*(?:standorte?|einsatzort|arbeitsort|location)\s*\n((?:[^\n]*\n){1,3})", markdown or "", re.I | re.M)
    if m:
        c = re.search(r"\b\d{4,5}\s+([A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ\w][\wäöüß.\-]*){0,2})", m.group(1))
        if c:
            return c.group(1).strip()
    return ""


def bare_city_under_heading(markdown: str) -> str:
    """ATS headers that print only the city under the H1 ('# Role\nMunich\nApply' on Greenhouse, '...\nMunich\nFull-time' on Personio).
    Weakest source: the next line must be an apply/employment-type line, and department words never count."""
    md = markdown or ""
    h1 = re.search(r"^#\s+.+$", md, re.M)
    if not h1:
        return ""
    lines = [l.strip() for l in md[h1.end():h1.end() + 300].splitlines() if l.strip()]
    if len(lines) >= 2 and re.fullmatch(r"[A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ][\wäöüß.\-]*)?", lines[0]) \
            and lines[0].lower() not in _NOT_A_CITY and _EMPLOYMENT_LINE.match(lines[1]):
        return lines[0]
    return ""


_NUM = r"\d{1,3}(?:[.,]\d{3})+|\d{4,6}"
_SALARY_RE = re.compile(rf"(?<![\d.,])({_NUM})\s*(?:€|EUR|Euro)?\s*(?:-|–|bis|to)\s*({_NUM})\s*(€|EUR|Euro)(?:\s*(?:brutto)?\s*(pro Monat|monatlich|pro Jahr|jährlich|per month|per year|/ ?Monat|/ ?Jahr|p\.a\.))?", re.I)
_SALARY_CONTEXT = re.compile(r"gehalt|salary|vergütung|brutto|pro monat|per month|jährlich|p\.a\.|/ ?jahr|/ ?monat|compensation", re.I)


def salary_from_text(markdown: str) -> str:
    """'4.800 € - 5.900 € pro Monat' stated in the posting body, only next to a salary word (never a bare number range)."""
    for m in _SALARY_RE.finditer(markdown or ""):
        around = (markdown or "")[max(0, m.start() - 120):m.end() + 60]
        if _SALARY_CONTEXT.search(around):
            return " ".join(m.group(0).split())
    return ""


# application-form fields never occur in posting text: everything from the first one on goes
_FORM_CUT = re.compile(
    r"^(?:\s*[*>\-]*\s*)(?:bewerben\s*\n+\s*oder\s*\n+\s*job teilen|#{1,4}\s*auf diesen job bewerben\s*$|meine daten\s*$|bitte geben sie ihre kontaktdaten an|vor- und nachname \*)",
    re.I | re.M,
)
# page footers / cookie managers: only the end of the text when no real section heading follows (a sticky footer or a
# privacy link in the middle of a page is followed by more posting text)
_FOOTER_CUT = re.compile(
    r"^(?:\s*[*>\-]*\s*)(?:"
    r"#{1,4}\s*\W*(?:ähnliche stellen|similar jobs|nützliche links|useful links|folge uns|follow us|navigation|diese website verwendet cookies|manager für cookie)"
    r"|ähnliche stellen|similar jobs"
    r"|\[?(?:datenschutz|impressum)[^\n]*\]?\s*(?:\||\[)"
    r"|\[(?:datenschutz\w*|impressum)\]"
    r"|cookie-einstellungen|cookies verwalten"
    r"|[\w ]+ verwendet cookies,"
    r"|bereitgestellt von|powered by"
    r"|share this job|back to job list|zurück zur (?:job)?liste|technical issues\?"
    r"|#{1,4}\s*(?:dein|ihr)e?\s+ansprechpartner(?:in)?\s*$|#{1,4}\s*(?:your )?contact person\s*$"
    r")",
    re.I | re.M,
)
# "Apply" buttons also sit in the middle of a page with more posting text below, so they only end the text when
# nothing but footer is left (no real section heading follows)
_APPLY_CUT = re.compile(r"^\s*[*>\-]*\s*(?:\[\s*(?:jetzt (?:online )?bewerben|apply now|apply for this job)\b|\[\s*apply\s*\]|(?:jetzt bewerben|apply now)\s*»?\s*$)", re.I | re.M)
_REAL_HEADING = re.compile(r"^#{1,4}\s+(?!.*(?:cookie|datenschutz|privacy|navigation|nützliche|useful|folge uns|follow us|ähnliche|similar))", re.I | re.M)
_COOKIE_BODY = re.compile(r"verwendet cookies|uses cookies|cookie-einstellungen|cookies (?:akzeptieren|ablehnen)|accept all cookies", re.I)


def has_chrome(text: str) -> bool:
    """True when the description still carries cookie-banner / footer text."""
    return bool(_COOKIE_BODY.search(text or "") or _FOOTER_CUT.search(text or ""))


_TAIL_CUT = re.compile(
    r"^(?:#{1,4}\s*\W*(?:manager für cookie|cookie|datenschutz-?einstellung|apply for this job|submit your application|similar jobs|ähnliche (?:stellen|jobs)|(?:diese|weitere) stellen könnten (?:auch )?interessant sein|you (?:might|may) also like|share this job|diesen job teilen)\b.*"
    r"|\s*(?:sitemap|©\s*\d{4}.*))$",
    re.I | re.M,
)


_SHARE_LINE = re.compile(r"^\s*[*\-•]\s*(?:\[\s*)?(?:whatsapp|linkedin|xing|telegram|facebook|twitter|x|pinterest|reddit|mail|e-?mail|e-mail teilen|link kopieren|drucken|print)\s*\]?(?:\(https?://[^)]*\))?\s*$", re.I)


def strip_inline_chrome(md: str) -> str:
    """Share-link bullets (WhatsApp/LinkedIn/XING...), Material icon names, empty '[](...)' links and a lone back-link."""
    out = []
    for line in md.splitlines():
        t = line.strip()
        if _SHARE_LINE.match(line) or t in _ICON_NAMES or re.fullmatch(r"(?:\[\s*\]\([^)]*\))+", t) \
                or re.fullmatch(r"(?:zurück zu den stellenangeboten|zurück zur übersicht|back to (?:all )?jobs)", t, re.I):
            continue
        out.append(line)
    return "\n".join(out)


def _cut_consent_dialog(md: str) -> str:
    """A consent dialog the browser could not dismiss (McKinsey/Avature) lands after the posting: cut from its first 'cookie'
    line when that is in the last 40% of the text and the rest of the page is mostly cookie talk."""
    pos = 0
    for line in md.splitlines(keepends=True):
        if pos > 0.6 * len(md) and re.search(r"cookie|privacy preference", line, re.I):
            if len(re.findall(r"cookie", md[pos:], re.I)) >= 3:
                return md[:pos].rstrip()
            break
        pos += len(line)
    return md


def _looks_like_nav(prefix: str) -> bool:
    lines = [l.strip() for l in prefix.splitlines() if l.strip()]
    if not lines:
        return False
    navish = sum(1 for l in lines if re.match(r"[*>\-\[]", l) or re.search(r"cookie|navigation|menü|menu", l, re.I))
    return navish / len(lines) >= 0.5


def _only_footer_left(rest: str) -> bool:
    return len(rest) < 800 or not _REAL_HEADING.search(rest)


def trim_chrome(markdown: str, title: str = "") -> str:
    """Start at the posting (the heading that carries the job title, else the H1 when only nav sits above it) and stop
    before application forms, footers and cookie managers."""
    md = strip_inline_chrome(markdown or "")
    t = _alnum(title)
    start = None
    if len(t) >= 10:   # landing page above the posting (career sites that put the job under a company intro)
        for h in re.finditer(r"^#{1,3}\s+(.+?)\s*$", md, re.M):
            ht = _alnum(h.group(1))
            if len(ht) >= 10 and (ht in t or t in ht):
                start = h.start() if h.start() > 300 else None
                break
    # a heading far down the page (recruiter contact block, "# Name") is not the start of the posting: never drop most of the text
    early = lambda pos: pos <= 0.4 * len(md)
    if start is not None:   # a heading that carries the job title is trusted wherever it sits (landing page above it)
        md = md[start:]
    else:
        h1 = re.search(r"^#\s+.+$", md, re.M)
        if h1 and h1.start() > 0 and early(h1.start()) and (h1.start() > 300 or _looks_like_nav(md[:h1.start()])):
            md = md[h1.start():]
        elif not h1:
            sub = re.search(r"^#{2,3}\s+(?!.*(?:cookie|navigation|menü|menu)).+$", md, re.M | re.I)
            if sub and sub.start() > 50:
                md = md[sub.start():]
    cut = _TAIL_CUT.search(md, 200)
    if cut:
        md = md[:cut.start()]
    md = _cut_consent_dialog(md)
    floor = max(400, int(len(md) * 0.3))
    form = _FORM_CUT.search(md, floor)
    if form:
        md = md[:form.start()]
    for foot in _FOOTER_CUT.finditer(md, floor):
        if _only_footer_left(md[foot.start():]):
            md = md[:foot.start()]
            break
    for apply_btn in _APPLY_CUT.finditer(md, floor):
        rest = md[apply_btn.start():]
        if len(rest) < 3500 and not _REAL_HEADING.search(rest):
            md = md[:apply_btn.start()]
            break
    return md.rstrip()


def first_heading(markdown: str) -> str:
    """H1, else the first usable H2/H3 (ELO JobPortal renders the title as ###)."""
    for pattern in (r"^#\s+(.+?)\s*$", r"^#{2,3}\s+(.+?)\s*$"):
        for m in re.finditer(pattern, markdown or "", re.M):
            found = _clean(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1)).strip("* "))
            if found and not re.search(r"cookie|navigation|menü|menu", found, re.I):
                return found
    return ""


def fields_from_metadata(meta: dict | None) -> dict:
    """title/company/description/location as stated in <title>, og:* and twitter:* tags."""
    meta = meta or {}
    get = lambda *keys: next((str(meta[k]) for k in keys if meta.get(k) not in (None, "None", "") and not is_placeholder(str(meta[k]))), "")
    site = get("og:site_name")
    gh = re.match(r"job application for .+ at (.+)$", get("title", "og:title"), re.I)  # Greenhouse
    title, company = split_title_company(next((t for t in (get("og:title"), get("twitter:title"), get("title")) if _clean(t)), ""), site)
    desc = get("og:description", "twitter:description", "description")
    if gh and not company:
        company = _clean(gh.group(1))
    return {
        "title": title,
        "company": company,
        "suffix_company": company_from_title_suffix(get("og:title"), get("title")),   # weakest source, used last
        "description": "" if is_placeholder(desc) else _html.unescape(desc).replace("\xa0", " ").strip(),
    }


def company_from_title_suffix(og_title: str, page_title: str) -> str:
    """<title> = og:title + ' - EDAG Group' / ' Stellendetails | HOERBIGER': the part after the role is the employer
    (last segment, generic page words like 'Stellendetails' dropped). Only when og:title is the bare role."""
    og, page = _clean(og_title), _clean(page_title)
    if not og or not page or not page.lower().startswith(og.lower()) or len(page) == len(og):
        return ""
    tail = page[len(og):]
    segments = [seg.strip() for seg in re.split(r"\s[|\-–—@]\s", " " + tail.strip() + " ") if seg.strip()]
    for seg in reversed(segments):
        seg = _clean_company(seg)
        if seg and len(seg) <= 40 and not re.search(r"stellen|detail|job|karriere|career|vacanc|posting|anzeige", seg, re.I):
            return seg
    return ""


def pick_css_hit(extracted) -> dict:
    """JsonCssExtractionStrategy returns a list of dicts (one per baseSelector match);
    merge them taking the first non-empty value per field."""
    if isinstance(extracted, dict):
        extracted = extracted.get("data", [extracted])
    if not isinstance(extracted, list):
        return {}
    merged: dict = {}
    for hit in extracted:
        if not isinstance(hit, dict):
            continue
        for key, value in hit.items():
            if isinstance(value, str):
                value = value.strip()
            if value and not merged.get(key):
                merged[key] = value
    return merged


def needs_render_retry(data: dict, markdown: str = "") -> bool:
    """Quality gate: blank/generic title, near-empty description or a loader shell means a JS page that needs a render wait."""
    return (not _clean(data.get("title")) or len(data.get("description") or "") < MIN_DESCRIPTION_CHARS
            or is_shell(data.get("description")) or is_shell(markdown) or is_cookie_page(data.get("description"))
            or is_nav_page(data.get("description")))


_NAV_HINT = re.compile(r"^\s*(?:#{1,4}\s*)?(?:verwandt|related jobs|ähnliche (?:stellen|jobs)|rechtliches|navigation|keywords|interessiert an dieser stelle\??|jobs suchen|für jobsuchende|share this job|back to job list)\s*$", re.I | re.M)
_AGGREGATORS = ("bebee.", "jooble.", "adzuna.", "jobted.", "talent.com", "kimeta.", "meinestadt.", "monster.", "neuvoo.", "jobrapido.", "careerjet.", "glassdoor.", "indeed.", "ziprecruiter.", "simplyhired.", "learn4good.")
_PASTE_CHROME = re.compile(
    r"easy apply|show match details|tailor my resume|create cover letter|help me stand out|did you finish applying|people clicked apply|responses managed off linkedin|"
    r"job match is (?:high|medium|low)|passt hervorragend|sei einer der ersten bewerber|basierend auf .{0,40}lebenslauf|erschienen: vor|verifiziert\s*$", re.I | re.M)


def is_cookie_page(text: str | None) -> bool:
    """A consent dialog / cookie declaration, not a posting (emagine's Cookiebot page was stored as 7k chars of 'description')."""
    t = text or ""
    n = len(re.findall(r"cookie", t, re.I))
    return n >= 6 and n * 1000 / max(1, len(t)) >= 2


def description_problems(description: str | None, url: str = "", pasted: bool = False) -> list[str]:
    """Everything wrong with a stored job description. A job description is non-negotiable (user rule 2026-10-27):
    every entry here must reach the user, so callers print them loudly and the daily routine reports each one."""
    d = (description or "").strip()
    n = len(d)
    out: list[str] = []
    if n == 0:
        out.append("description MISSING: nothing was extracted")
    elif n < MIN_DESCRIPTION_CHARS:
        out.append(f"description TOO SHORT ({n} chars): JS page, teaser or error page, not the posting")
    elif n < 600:
        out.append(f"description is short ({n} chars): check that it is the full posting")
    if n and (is_shell(d) or is_placeholder(d[:60])):
        out.append("description is a loader/placeholder page, not the posting")
    if n and is_cookie_page(d):
        out.append("description is a cookie banner / consent dialog, not the posting")
    if pasted:
        if _PASTE_CHROME.search(d):
            out.append("pasted text still contains page chrome (LinkedIn/StepStone UI lines)")
    else:
        if has_chrome(d) or _NAV_HINT.search(d):
            out.append("description still contains cookie/footer/navigation text")
        links = len(re.findall(r"\]\(https?://", d))
        if n and links >= 10 and links * 1000 / n >= 4:
            out.append(f"description has {links} links (navigation/footer text left?)")
        host = (urlparse(url or "").hostname or "").lower()
        if any(a in host + "/" for a in _AGGREGATORS):
            out.append(f"description comes from an aggregator ({host}), not the employer's own page")
    return out


def _alnum(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def is_nav_page(text: str | None) -> bool:
    """Mostly a link list (mega-menu, sitemap): the page served navigation, not a posting."""
    d = text or ""
    links = len(re.findall(r"\]\(https?://", d))
    return bool(d) and links >= 10 and links * 1000 / len(d) >= 4


_LINK_ONLY_LINE = re.compile(r"^\s*(?:[*\-•]\s*)?\[[^\n]*\]\((?:https?://|/|tel:|mailto:|#)[^\n]*\)\s*/?\s*$|^\s*(?:zurück|back)\s*$", re.I)


def strip_link_lines(md: str) -> str:
    """Drop lines that are only links ('* [ Pharma ](https://...)') from a link-heavy page, so what is left shows
    whether any posting text was served at all."""
    return "\n".join(l for l in (md or "").splitlines() if not _LINK_ONLY_LINE.match(l)).strip()


def has_prose(text: str | None) -> bool:
    """At least three real sentences-worth lines (>= 60 chars, >= 8 words): menus and address blocks never reach that."""
    return sum(1 for l in (text or "").splitlines() if len(l.strip()) >= 60 and len(l.split()) >= 8) >= 3


def cut_trailing_link_blocks(md: str) -> str:
    """Remove the run of link-only lines, headings and blanks at the very end ('Jetzt bewerben', 'Über X', footer
    link lists, 'Rechtliches') once it holds at least three link lines; text above it is never touched."""
    lines = (md or "").rstrip().splitlines()
    i = len(lines)
    links = 0
    while i > 0:
        l = lines[i - 1].strip()
        if not l or l.startswith("#"):
            i -= 1
        elif _LINK_ONLY_LINE.match(l) or re.fullmatch(r"\[[^\]]*\]\([^)]*\)\s*", l):
            links += 1
            i -= 1
        else:
            break
    return "\n".join(lines[:i]).rstrip() if links >= 3 else (md or "").rstrip()


def dedupe_repeat(md: str) -> str:
    """Some career sites print the whole posting twice (once per layout): cut at the second copy of the opening block.
    When the text after the second copy is much longer than the first block, only the lead-in is repeated (og:description of
    onlyfy pages: 'intro. intro. duties...'): drop the first copy and keep everything else."""
    md = (md or "").strip()
    probe = md[:200]
    if len(probe) < 200:
        return md
    again = md.find(probe, 100)
    if again <= 0:
        return md
    if len(md) - again > 1.3 * again:
        return md[again:].lstrip()
    return md[:again].rstrip()


_FORM_START = re.compile(r"\n\s*(?:Apply\s*\n\s*or\s*\n|My information\s*\n|Fill out the information below)", re.I)


def cut_application_form(md: str) -> str:
    """Recruitee pages end with the whole application form (CV upload, questions, consent text, 'All done!' banners)."""
    m = _FORM_START.search(md or "")
    return md[:m.start()].rstrip() if m and m.start() > 300 else (md or "")


_ROLE_OR_TERMS = re.compile(r"\b(vollzeit|teilzeit|full[- ]?time|part[- ]?time|hybrid\w*|remote|homeoffice|home[- ]office|mobil\w*|absolvent\w*|berufseinsteiger|"
                            r"werkstudent\w*|praktik\w*|festanstellung|unbefristet|befristet|senior|junior|professionals?|führungskräfte|arbeiten|m/w/d|gn|ausbildung|studium)\b", re.I)
_FACT_LOCATION = re.compile(r"[A-ZÄÖÜ][\wäöüß.\-]+(?: ?[/,·] ?[A-ZÄÖÜ][\wäöüß.\-]+){0,3}")
_LEGAL_ANY = re.compile(rf"\b(?:{_LEGAL_FORMS})(?:\s|$)")


def header_facts(markdown: str, title: str = "") -> dict:
    """Short fact lines printed just above the breadcrumb / title heading ('EDAG PS GmbH & Co. KG', 'Hybrides Arbeiten
    möglich', 'Fulda / Ingolstadt', 'Vollzeit'): legal-form line = company, a bare capitalised place line = location."""
    md = markdown or ""
    t = _alnum(title)
    head = None
    for h in re.finditer(r"^#{1,3}\s+(.+?)\s*$", md, re.M):
        ht = _alnum(h.group(1))
        if t and len(t) >= 10 and len(ht) >= 10 and (ht in t or t in ht):
            head = h
            break
    if not head:
        return {}
    lines = [l.strip() for l in md[:head.start()].splitlines()]
    while lines and (not lines[-1] or len(re.findall(r"\]\(", lines[-1])) >= 2):   # blank lines, breadcrumb row
        lines.pop()
    facts: list[str] = []
    for l in reversed(lines):
        if not l or "](" in l or l.startswith(("#", "*", "-", "|")) or len(l) > 60:
            break
        facts.append(l)
        if len(facts) == 6:
            break
    out: dict = {}
    for l in reversed(facts):
        if _LEGAL_ANY.search(l) and not out.get("company"):
            out["company"] = l.strip(" ,")
        elif not _ROLE_OR_TERMS.search(l) and _FACT_LOCATION.fullmatch(l) and not l.isupper() \
                and l.lower() not in _NOT_A_CITY and not out.get("location"):
            out["location"] = l
    return out


def merge_job_fields(css: dict, meta: dict | None, markdown: str, page_html: str | None = None, url: str = "") -> dict:
    """Combine CSS hits, page metadata, JSON-LD and markdown. Only values the page states; no guessing.
    `url` is used only to confirm an employer name that the page text also writes (company_from_host)."""
    from_meta = fields_from_metadata(meta)
    raw_markdown = markdown or ""
    ld = fields_from_jsonld(page_html)
    title = ld.get("title") or _clean(css.get("title")) or from_meta["title"]
    markdown = trim_chrome(strip_placeholder(raw_markdown), title)
    title = title or first_heading(markdown)
    title = re.sub(r"^(?:wir suchen|we(?:'re| are) (?:looking for|hiring)|gesucht:?)\s+", "", title, flags=re.I).strip()   # "Wir suchen Backend Developer"
    labels = labelled_fields(markdown if len(markdown) > 300 else raw_markdown)
    # trim_chrome starts at the posting, which can cut the 'Einsatzort: Schongau' block printed above it
    if not labels.get("location"):
        labels["location"] = labelled_fields(raw_markdown).get("location", "")
    facts = header_facts(raw_markdown, title)
    had_placeholder = bool(_PLACEHOLDER_RE.search(raw_markdown))
    company = _clean_company(labels.get("company")) or ld.get("company") or _clean_company(css.get("company")) or _clean_company(from_meta["company"])
    # a "company" that is just part of the title (or a "Jobs bei" crumb) is a selector mismatch
    def _bad_company(c: str) -> bool:
        return not c or c.lower() in title.lower() or bool(re.search(r"\b(jobs?|karriere|careers?)\s+(bei|at)\b", c, re.I))

    if _bad_company(company):
        company = "" if _bad_company(_clean_company(from_meta["company"])) else _clean_company(from_meta["company"])
    company_source = "page" if company else ""
    if not company:
        company = company_from_host(url, raw_markdown + "\n" + from_meta["description"])
        company_source = "host+text" if company else ""
    if not company:
        company = from_meta.get("suffix_company") or facts.get("company", "")
        company_source = "title-suffix/header" if company else ""
    company = complete_legal_form(company, raw_markdown)

    # description: page markdown, minus chrome. A full og:description / JSON-LD text is cleaner than markdown only when it
    # is nearly as long (>= 85%; a shorter one is a teaser or a partial copy); a 1-char JS shell never wins. No "JSON-LD is complete" guessing:
    # some sites put only the intro and benefits in JSON-LD while tasks and profile sit elsewhere on the page.
    og_desc = from_meta["description"]
    css_desc = strip_placeholder(css.get("description") or "").strip()
    markdown = markdown.strip()
    ld_desc = ld.get("description", "")
    if len(ld_desc) >= 500:
        og_desc = ld_desc
    # a one-line copy (JSON-LD that glues "...gesehen.Umfassende...") loses the bullets the markdown still has
    flat_copy = og_desc.count("\n") < 3 and markdown.count("\n") >= 5
    if len(og_desc) >= 500 and len(og_desc) >= 0.85 * len(markdown) and not flat_copy:
        description = og_desc
    else:
        description = max([markdown, og_desc, css_desc], key=len)

    nav_only = False
    if is_nav_page(description):
        description = strip_link_lines(description)   # what is left shows that no posting text came with the menus
        nav_only = not has_prose(description)
    description = cut_application_form(cut_trailing_link_blocks(dedupe_repeat(description)))

    fields = field_list(raw_markdown)
    ld_place = ld.get("location", "")
    ld_weak = len(ld_place) <= 3   # JSON-LD with only a country code ("DE") says nothing about the city
    location = (labels.get("location") or fields.get("location") or icon_location(raw_markdown)
                or ("" if ld_weak else ld_place) or _clean_location(css.get("location")) or heading_location(raw_markdown)
                or bullet_location(raw_markdown) or job_id_cities(raw_markdown) or postcode_location(raw_markdown) or bare_city_under_heading(raw_markdown)
                or facts.get("location", "") or (ld_place if ld_weak else ""))
    location = location or location_list(raw_markdown) or homeoffice_location(raw_markdown) or standort_phrase(from_meta["description"])
    # aggregated ATS titles end with the place ("AI Engineer (Germany) in Munich, German, Germany")
    if location.count(",") >= 1 and title.lower().endswith(" in " + location.lower()):
        title = title[:-len(location) - 4].rstrip()
    if location and ld.get("remote") and "remote" not in location.lower():
        location += " (remote)"
    salary = css.get("salary") or ld.get("salary") or fields.get("salary") or salary_from_text(description) or ""

    warnings = [f"{f} blank" for f, v in (("company", company), ("location", location)) if not v]
    warnings += description_problems(description, url)

    return {
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "description": description,
        # template page (e.g. SuccessFactors preview): body is Lorem Ipsum, no posting text served
        "nav_only": nav_only,   # the page served menus/footer only (job list or JS app): no posting text exists in it
        "placeholder_only": had_placeholder and not ld.get("description") and len(from_meta["description"]) < 500,
        "requirements": css.get("requirements") or "",
        "benefits": css.get("benefits") or "",
        "company_source": company_source,
        "warnings": warnings,
    }
