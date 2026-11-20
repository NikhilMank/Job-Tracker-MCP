"""Plain-script tests for job_extract.py; exits 1 on failure. Run from project root."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import job_extract
from job_extract import *

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

check("split site", split_title_company("AI Engineer (m/w/d) | Acme", "Acme"), ("AI Engineer (m/w/d)", "Acme"))
check("split two-part", split_title_company("ML Engineer - Acme GmbH"), ("ML Engineer", "Acme GmbH"))
check("split long tail kept", split_title_company("Senior Engineer - Platform Team for Cloud Data Systems"), ("Senior Engineer - Platform Team for Cloud Data Systems", ""))
check("placeholder og", fields_from_metadata({"og:title": "Lorem Ipsum", "title": "Machine Learning & AI Eng. (d/m/w)"})["title"], "Machine Learning & AI Eng. (d/m/w)")
check("generic title dropped", fields_from_metadata({"title": "Jobs"})["title"], "")
check("strip lorem", strip_placeholder("Lorem ipsum dolor sit amet\n\nReal text here"), "Real text here")
check("retry blank title", needs_render_retry({"title": "", "description": "x" * 500}), True)
check("retry short desc", needs_render_retry({"title": "T", "description": "x"}), True)
check("no retry", needs_render_retry({"title": "T", "description": "x" * 500}), False)
check("css merge list", pick_css_hit([{"title": ""}, {"title": "A", "company": "B"}]), {"title": "A", "company": "B"})
og = "Job Description: " + "word " * 200
m = merge_job_fields({}, {"og:title": "Role", "og:description": og}, "x")
m = merge_job_fields({}, {}, "# Backend Dev\n\n" + "text " * 100)

ld = '<script type="application/ld+json">{"@type":"JobPosting","title":"AI Eng &amp; Co","hiringOrganization":{"name":"Acme"},"jobLocation":{"address":{"addressLocality":"Ulm","addressCountry":"DE"}},"description":"<p>Hello</p><ul><li>One</li></ul>"}</script>'
f = fields_from_jsonld(ld)
check("jsonld", (f["title"], f["company"], f["location"], f["description"]), ("AI Eng & Co", "Acme", "Ulm, DE", "Hello\nOne"))
check("gender tail not company", split_title_company("AI / ML Engineer - Agentic AI ( m/w/d)"), ("AI / ML Engineer - Agentic AI ( m/w/d)", ""))
check("company inside title dropped", merge_job_fields({"title": "Backend Eng", "company": "Backend Eng"}, {}, "x")["company"], "")
check("Jobs bei dropped", merge_job_fields({"title": "T", "company": "Jobs bei"}, {"og:site_name": "Jobs bei"}, "x")["company"], "")

check("org code", (job_extract._strip_org_code("1000 Initech SE"), job_extract._strip_org_code("922E Hooli Defence and Space"), job_extract._strip_org_code("3M Deutschland")), ("Initech SE", "Hooli Defence and Space", "3M Deutschland"))
check("placeholder page flagged", merge_job_fields({}, {"title": "Real Title"}, "# Lorem Ipsum\n\nLorem ipsum dolor sit amet\n\nnav " * 3)["placeholder_only"], True)
check("normal page not flagged", merge_job_fields({}, {}, "# Dev\n\n" + "text " * 100)["placeholder_only"], False)
check("shell detected", is_shell("[JobPortal](/x)\nLoading data...\npowered by ELO"), True)
check("jobportal title generic", fields_from_metadata({"title": "JobPortal"})["title"], "")
check("gate: shell + generic title", needs_render_retry({"title": "JobPortal", "description": "x" * 440 + " Loading data"}), True)
check("h3 title fallback", first_heading("nav\n\n### AI-Engineer (m/w/d)\n###  Festanstellung\ntext"), "AI-Engineer (m/w/d)")
check("labels", labelled_fields("**Unternehmen:** Initech\n**Standort:** Düsseldorf, DE"), {"company": "Initech", "location": "Düsseldorf, DE"})
check("label beats footer site_name", merge_job_fields({}, {"og:title": "T", "og:site_name": "Dr. Ing. h.c. F. Globex AG"}, "# T\n**Gesellschaft:** Globex Consulting GmbH\n" + "x " * 200)["company"], "Globex Consulting GmbH")
check("greenhouse company", fields_from_metadata({"title": "Job Application for Applied AI Engineer, Enterprise at Acme", "og:title": "Applied AI Engineer, Enterprise"})["company"], "Acme")
check("h2 above h1 is location", heading_location("nav\n\n## Bamberg\n# AI Engineer\ntext"), "Bamberg")
check("city line under h1", heading_location("# Applied AI Engineer\nMunich, Germany\nApply"), "Munich, Germany")
check("job-code line is not a location", heading_location("# AI Solution Engineer\nJob-Code: J000021916\nX"), "")
check("glued location label", merge_job_fields({"title": "T", "location": "LocationDortmund"}, {}, "# T\n" + "x " * 200)["location"], "Dortmund")
check("cookie manager cut", trim_chrome("# Job\n" + "text " * 80 + "\n## Manager für Cookie-Einwilligungen\nfoo").endswith("text"), True)

# --- helpers added 2026-10-21 (tectake / Zurich / KB Marketing / Birds on Mars failures) ---
check("entities decoded", fields_from_metadata({"og:title": "Junior Specialist Automation &amp; AI (m/w/d)"})["title"], "Junior Specialist Automation & AI (m/w/d)")
check("career prefix", (job_extract._clean_company("Jobs@Birds on Mars"), job_extract._clean_company("Karriere bei Acme GmbH"), job_extract._clean_company("Jobs bei")), ("Birds on Mars", "Acme GmbH", ""))
check("domain is not a company", job_extract._clean_company("karriere-kbmarketing.de"), "")
check("legal form from text", complete_legal_form("Birds on Mars", "Birds on Mars GmbH ist eine auf Daten spezialisierte Beratung"), "Birds on Mars GmbH")
check("legal form not invented", complete_legal_form("Acme", "Acme builds things"), "Acme")
check("host + text company", (company_from_host("https://tectakegmbh.factorialhr.de/job/1", "tectake ist ein Unternehmen"), company_from_host("https://www.careers.zurich.com/job/x", "Bei Zurich leben wir"), company_from_host("https://exmox-gmbh.jobs.personio.com/job/2", "At exmox we build")), ("tectake", "Zurich", "exmox"))
check("host not backed by text", company_from_host("https://tectakegmbh.factorialhr.de/job/1", "no brand name here"), "")
check("platform host gives nothing", company_from_host("https://jobs.ashbyhq.com/x/1", "ashbyhq jobs"), "")
check("bullet location", bullet_location("# Role\n  * Unbefristet \n  * Vollzeit \n  * Höchberg, Bayern, Deutschland \n\ntext"), "Höchberg, Bayern, Deutschland")
check("bullet that is not a place", bullet_location("# Role\n  * Berlin, Hamburg, München\n"), "")
check("salary from text", salary_from_text("Dein Einstiegsgehalt liegt zwischen 4.800 und 5.900 € brutto monatlich"), "")  # 'und' form is not parsed on purpose
check("salary range with unit", salary_from_text("Gehalt: 4.800 € - 5.900 € pro Monat"), "4.800 € - 5.900 € pro Monat")
check("bare range is not a salary", salary_from_text("Seit 2015 haben wir 1.000 - 2.000 € Umsatz"), "")
check("jsonld salary", fields_from_jsonld('<script type="application/ld+json">{"@type":"JobPosting","title":"T","baseSalary":{"currency":"EUR","value":{"minValue":4800.0,"maxValue":5.9e3,"unitText":"MONTH"}},"jobLocationType":"TELECOMMUTE"}</script>')["salary"], "4800 - 5900 EUR per month")
check("jsonld remote flag", fields_from_jsonld('<script type="application/ld+json">{"@type":"JobPosting","title":"T","jobLocationType":"TELECOMMUTE"}</script>')["remote"], True)
check("footer cut keeps body", trim_chrome("# Job\n" + "body text. " * 80 + "\n\nÄhnliche Stellen suchen:\n  * [Datenschutz](x)\n").endswith("body text."), True)
check("apply button cut", trim_chrome("# Job\n" + "body text. " * 80 + "\n[Jetzt bewerben ](https://x/apply)\n[Datenschutz](x)").endswith("body text."), True)
check("nav above h1 dropped", trim_chrome("[](https://x/)\n  * [Stellen](https://x/#jobs)\n  * >\n# Role\n" + "body " * 80).startswith("# Role"), True)
check("short prose before h1 kept", trim_chrome("Intro sentence before the title.\n# Role\n" + "body " * 80).startswith("Intro"), True)

check("jsonld country code upper", fields_from_jsonld('<script type="application/ld+json">{"@type":"JobPosting","title":"T","jobLocation":{"address":{"addressLocality":"Köln","addressCountry":"de"}}}</script>')["location"], "Köln, DE")

# --- regression cases from real-world scraper failures (inputs rewritten with placeholder companies) ---
check("field list bold location", field_list("**Location**\nGermany \nBayern \nErlangen \nRemote vs. Office \nHybrid"), {"location": "Erlangen, Bayern, Germany"})
check("field list collapses repeats", field_list("**Location**\nSpain \nBarcelona \nBarcelona \n  * Country: SPAIN\n"), {"location": "Barcelona, Spain"})
check("field list plain label = one line", field_list("Ort\nKöln\nIndustry\nData & AI\nGehalt pro Jahr\n&#8364;74,000.00 EUR\n"), {"location": "Köln", "salary": "€74,000.00 EUR"})
check("field list ignores prose", field_list("Ort\nWir sind (m/w/d) überall: Berlin"), {})
check("jsonld region when no city", fields_from_jsonld('<script type="application/ld+json">{"@type":"JobPosting","title":"T","jobLocation":{"address":{"addressCountry":"Spain","addressRegion":"Barcelona"}}}</script>')["location"], "Barcelona, Spain")
check("apply button cut (Avature)", trim_chrome("# Job\n" + "body text. " * 80 + "\n[ Apply ](https://x/login)\nShare this job: \n  * Email\n").endswith("body text."), True)
check("application form + contact person cut", trim_chrome("# Job\n" + "body text. " * 80 + "\n### Dein Ansprechpartner\nA B\n+49 1\n### Auf diesen Job bewerben\nName*\nE-mail*\n").endswith("body text."), True)
# --- a missing/broken job description must always be reported (e.g. aggregator pages) ---
check("desc missing", description_problems("")[0].startswith("description MISSING"), True)
check("desc too short", description_problems("x" * 50)[0].startswith("description TOO SHORT"), True)
check("desc short warning", description_problems("word " * 100)[0].startswith("description is short"), True)
check("desc fine", description_problems("word " * 300, "https://jobs.acme.de/x"), [])
check("desc shell", any("loader" in w for w in description_problems("Loading data... powered by ELO")), True)
bebee = "Posting text. " * 80 + "\nKeywords\nartificial-intelligence\nInteressiert an dieser Stelle?\n## Verwandt\n" + "[a](https://bebee.com/x)" * 12
check("desc aggregator chrome", (any("navigation" in w for w in description_problems(bebee, "https://bebee.com/de/jobs/x")), any("aggregator" in w for w in description_problems(bebee, "https://bebee.com/de/jobs/x")), any("links" in w for w in description_problems(bebee, "https://x.de"))), (True, True, True))
check("pasted LinkedIn chrome", any("chrome" in w for w in description_problems("Easy Apply\nShow match details\n" + "word " * 200, pasted=True)), True)
check("clean paste", description_problems("Aufgaben und Profil. " * 60, pasted=True), [])
check("merge reports empty description", any("MISSING" in w for w in merge_job_fields({}, {"og:title": "T"}, "", None, "https://x.de/j")["warnings"]), True)
check("late contact H1 does not cut the posting", trim_chrome("Intro line.\n" + "posting text. " * 300 + "\n## Contact\n# Pat Example\nRecruiter\n").startswith("Intro line."), True)
check("cookie page detected", (is_cookie_page("This website uses cookies. " * 10 + "Cookie Declaration"), is_cookie_page("Aufgaben " * 300 + "Wir nutzen Cookies.")), (True, False))
check("cookie page forces render retry", needs_render_retry({"title": "T", "description": "We use cookies. " * 40}), True)
check("cookie page is a hard description problem", any("cookie banner" in w for w in description_problems("We use cookies. " * 40)), True)
check("similar jobs list cut (Workday)", trim_chrome("## Job\n" + "body text. " * 80 + "\n### Similar Jobs (5)\n#### [Other Role](https://x/1)\n#### [Third Role](https://x/2)\n").endswith("body text."), True)
# --- regression cases from real-world scraper failures (inputs rewritten with placeholder companies) ---
FILL = "word " * 120
check("form label is not a location", (job_extract._clean_location("E-Mail*"), job_extract._clean_location("All"), job_extract._clean_location("Vor Ort"), job_extract._clean_location("LocationDortmund")), ("", "", "", "Dortmund"))
check("greenhouse bare city", bare_city_under_heading("# AI Systems Engineer (m/f/d)\nMunich\nApply\n_Founded in 2016_"), "Munich")
check("personio bare city", bare_city_under_heading("# AI Engineer - Simulation\nMunich\nFull-time\nPermanent employee"), "Munich")
check("department is not a city", bare_city_under_heading("# Role\nEngineering\nFull-time\ntext"), "")
check("icon header location", icon_location("#  AI Engineer\nSSF\nlocation_on\nMünchen, Berlin\ntimer\nVollzeit"), "München, Berlin")
check("postcode location", postcode_location("  * ## Standort\nAm Campus 1  \n74177 Bad Friedrichshall \n  * ## Abteilung\nIT"), "Bad Friedrichshall")
ld_de = '<script type="application/ld+json">{"@type":"JobPosting","title":"T","jobLocation":{"address":{"addressCountry":"DE"}}}</script>'
check("country-only JSON-LD loses to the page", merge_job_fields({"title": "T"}, {}, "# T\n  * ## Standort\nAm Campus 1\n74177 Bad Friedrichshall\n" + FILL, ld_de)["location"], "Bad Friedrichshall")
check("country-only JSON-LD still used as last resort", merge_job_fields({"title": "T"}, {}, "# T\n" + FILL, ld_de)["location"], "DE")
check("icon header beats JSON-LD city", merge_job_fields({"title": "T"}, {}, "# T\nlocation_on\nMünchen, Berlin\n" + FILL, '<script type="application/ld+json">{"@type":"JobPosting","title":"T","jobLocation":{"address":{"addressLocality":"München","addressCountry":"DE"}}}</script>')["location"], "München, Berlin")
check("css form label ignored", merge_job_fields({"title": "T", "location": "E-Mail*"}, {}, "# T\n" + FILL)["location"], "")
check("title place suffix dropped", merge_job_fields({"title": "AI Engineer (Germany) in Munich, German, Germany", "location": "Munich, German, Germany"}, {}, "# x\n" + FILL)["title"], "AI Engineer (Germany)")
check("title with 'in' kept", merge_job_fields({"title": "Engineer in Test", "location": "Berlin"}, {}, "# x\n" + FILL)["title"], "Engineer in Test")
share = "# Role\nJetzt bewerben\n  * [WhatsApp](https://api.whatsapp.com/send?text=x)\n  * [LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=x)\n  * [XING](https://www.xing.com/share?url=x)\n  * Mail\n\n\n  * ## Standort\nAm Campus 1\n" + "body text. " * 80
sh = trim_chrome(share)
check("share links dropped, posting kept", ("whatsapp" in sh.lower(), "xing" in sh.lower(), "Standort" in sh, "body text." in sh), (False, False, True, True))
tail = "# Role\n" + "body text. " * 80 + "\n##  Dein Ansprechpartner\nA B\n##  Diese Stellen könnten auch interessant sein\n[Other](https://x/1)\n###  Other Role(m/w/d)\n###  Initiativbewerbung\n© 2026 Acme Digits\n"
check("'other jobs' list, recruiter block and copyright cut", trim_chrome(tail).endswith("body text."), True)
ssf = "[](/)\narrow_back\nzurück zu den Stellenangeboten\n#  AI Engineer (m/w/d)\nAcme Engineering AG\nlocation_on\nMünchen, Berlin\ntimer\nVollzeit\ncalendar_clock\nAb sofort\nwork\nBerufserfahrene\nJetzt bewerben\n## Ihre Aufgaben\n" + "body text. " * 80 + "\n### SSF Ingenieure.\nBegeisterung für Engineering.\nSitemap\n[ Über uns ](https://x/)\nRechtliches\n[ Datenschutz ](/datenschutz)\n"
ss = trim_chrome(ssf, "AI Engineer (m/w/d)")
check("ssf: icons, back link and sitemap footer gone", ("arrow_back" in ss, "timer" in ss, "Sitemap" in ss, "Datenschutz" in ss, "Ihre Aufgaben" in ss, "München, Berlin" in ss), (False, False, False, False, True, True))

check("share heading + empty icon links cut", trim_chrome("# Role\n" + "body text. " * 80 + "\n## Share This Job\n[](https://x/1)[](https://x/2)\n").endswith("body text."), True)
check("avature job id cities", job_id_cities("# Software Engineer\nJob ID: 114023\n  * Cologne\n  * Dusseldorf\n  * Munich\n\n\nApply Now"), "Cologne, Dusseldorf, Munich")
check("bullets without Job ID are not cities", job_id_cities("# Role\n  * Python\n  * Docker\n"), "")
dialog = "# Role\n" + "posting text. " * 200 + "\nWe use cookies to improve your experience.\nAccept All CookiesDecline optional cookies\n## Privacy Preference Center\nThese cookies are strictly necessary cookies.\n" * 1
check("undismissed consent dialog after the posting is cut", trim_chrome(dialog).endswith("posting text."), True)
check("one cookie word in the posting is kept", trim_chrome("# Role\n" + "posting text. " * 100 + "\nWe bake cookies on Fridays.\n" + "more text. " * 20).endswith("more text."), True)
check("header_facts", header_facts("# SLOGAN\nACME GmbH\nHybrides Arbeiten möglich\nBerlin\nVollzeit\n[Start](/) [Jobs](/jobs)\n## Backend Engineer (m/w/d)\ntext", "Backend Engineer (m/w/d)"), {"company": "ACME GmbH", "location": "Berlin"})
check("title suffix company", (company_from_title_suffix("AI Eng (m/w/d)", "AI Eng (m/w/d) - Acme Group"), company_from_title_suffix("AI Eng", "AI Eng Stellendetails | ACME"), company_from_title_suffix("AI Eng", "AI Eng | Stellendetails")), ("Acme Group", "ACME", ""))
check("split generic head", split_title_company("Jobs | acme group"), ("", "acme group"))
check("nav page detection", (is_nav_page("[a](https://x/1)\n" * 20), is_nav_page("prose " * 300)), (True, False))
check("trailing link block cut only with 3+ links", (cut_trailing_link_blocks("text\n[a](/1)\n[b](/2)").endswith("[b](/2)"), cut_trailing_link_blocks("text\n## Rechtliches\n[a](/1)\n[b](/2)\n[c](/3)")), (True, "text"))
# --- regression cases from real-world scraper failures (inputs rewritten with placeholder companies) ---
_intro = "AI Engineer (w/m/d) für den Standort Starnberg (Percha) Sie moechten einen wertvollen Beitrag fuer die Gesundheit von Patient*innen leisten? Und eigenverantwortlich etwas wirklich Sinnvolles bewirken? Dann freuen wir uns auf Sie! Excellence beyond manufacturing."
_body = " Ihr Aufgabengebiet Sie entwickeln und betreiben skalierbare KI-Agenten. Ihr Profil Sie bringen Python mit." * 12
check("dedupe: repeated lead-in keeps the posting", dedupe_repeat(_intro + " " + _intro + _body).count("Ihr Aufgabengebiet"), 12)
check("dedupe: whole posting twice is still cut", dedupe_repeat(("Zeile eins " + "x" * 300 + "\n") * 2 + "y").count("Zeile eins"), 1)
check("platform name is not a company", (job_extract._clean_company("onlyfy.jobs"), job_extract._clean_company("Jobs.recruitee"), job_extract._clean_company("Acme Group")), ("", "", "Acme Group"))
check("hyphenated host company", company_from_host("https://i-acme.net/jobs/backend-ai-engineer", "Du baust das Backend. i-acme GmbH, Koeln. Auf ai-acme entstehen Loesungen"), "i-acme GmbH")
check("Wir suchen prefix", merge_job_fields({}, {"og:title": "Wir suchen Backend Developer"}, "x")["title"], "Backend Developer")
check("Globex Location(s) block", location_list("Company \nGlobex AG \nLocation(s) \n  * Munich - - Germany \n\n\n**We are ONE Globex**"), "Munich, Germany")
check("recruitee nested bullets + doubled city", bullet_location("# Voice AI Engineer\n  * Hybrid\n  *     * Berlin, Berlin, Germany\n  * Product Development\n"), "Berlin, Germany")
check("Koeln mit Homeoffice", homeoffice_location("Jetzt Kontakt aufnehmen\nKöln mit Homeoffice\n# Backend Developer"), "Köln")
check("fuer den Standort", standort_phrase("AI Engineer (w/m/d) für den Standort Starnberg (Percha) Sie möchten"), "Starnberg (Percha)")
check("application form cut", cut_application_form("Posting text. " * 40 + "\nApply\nor\nApply with Indeed\nMy information\nFull name *").endswith("Posting text."), True)
check("short text with form words is left alone", cut_application_form("Hi\nApply\nor\nApply with Indeed"), "Hi\nApply\nor\nApply with Indeed")
m = merge_job_fields({}, {"og:title": "AI Engineer (w/m/d)", "og:site_name": "onlyfy.jobs", "og:description": _intro + " " + _intro + _body},
                     "[All jobs](https://x/en)\nEN\n", None, "https://aenova-group.onlyfy.jobs/en/job/abc")
check("onlyfy page: full text, not platform name", (len(m["description"]) > 1500, m["company"], m["location"]), (True, "", "Starnberg (Percha)"))

# --- synthetic pages, one per common page shape (no third-party content) ---
FILLER = "Responsibilities and requirements for this role. " * 30
def merged(css=None, meta=None, md="", ld=None, url="https://jobs.example.com/x"):
    return merge_job_fields(css or {}, meta or {}, md, ld, url)
# 1. JS single-page app: markdown is empty, all facts come from JSON-LD
ld_spa = '<script type="application/ld+json">{"@type":"JobPosting","title":"ML Engineer","hiringOrganization":{"name":"Acme Labs"},"description":"' + FILLER + '","jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"DE"}},"baseSalary":{"currency":"EUR","value":{"minValue":60000,"maxValue":75000,"unitText":"YEAR"}}}</script>'
spa = merged(md="x", ld=ld_spa)
check("synthetic SPA: title/company/location", (spa["title"], spa["company"], spa["location"]), ("ML Engineer", "Acme Labs", "Berlin, DE"))
check("synthetic SPA: description from JSON-LD", len(spa["description"]) > 500, True)
# 2. Page with nav above the title, a bare city under the H1, an apply form and a footer
chrome = "[](https://example.com/)\n  * [Jobs](https://example.com/jobs)\n  * >\n# Backend Engineer (m/f/d)\nMunich\nFull-time\n## Your tasks\n" + FILLER + "\n### Auf diesen Job bewerben\nName*\nE-mail*\n"
pg = merged(md=chrome, meta={"og:title": "Backend Engineer (m/f/d) - Acme Labs"})
check("synthetic chrome page: title/company/location", (pg["title"], pg["company"], pg["location"]), ("Backend Engineer (m/f/d)", "Acme Labs", "Munich"))
check("synthetic chrome page: nav, form dropped", ("[Jobs]" in pg["description"], "E-mail*" in pg["description"], "Your tasks" in pg["description"]), (False, False, True))
# 3. A job-list / nav-only page never contains the posting
lst = merged(md="[a](https://example.com/1)\n" * 25, meta={"title": "Jobs | Acme Labs"})
check("synthetic job list: nav_only, no title, render retry", (lst["nav_only"], lst["title"], needs_render_retry(lst)), (True, "", True))
# 4. Cookie-consent shell instead of a posting
ck = merged(md="This website uses cookies. " * 40, meta={"title": "Backend Engineer"})
check("synthetic cookie shell is reported", any("cookie" in w.lower() for w in ck["warnings"]), True)
print("\n".join(fails) or "all passed")
sys.exit(1 if fails else 0)
