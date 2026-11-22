"""Shared AI-role detection for job-letter and job-suggestion mail (used by scan_company_jobletters.py and clean_job_suggestions.py)."""
import json, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
# The user's own role keywords live in data/role_keywords.json (git-ignored), never in this tracked file, so updates cannot overwrite them:
#   {"core": ["nurse", "icu"], "related": ["care assistant"], "exclude": ["volunteer"]}
# "core" / "related" REPLACE the defaults below (they target AI/ML roles); "exclude" ADDS to the not-full-time words.
OVERRIDE_PATH = os.path.join(ROOT, "data", "role_keywords.json")

CORE = re.compile(r"(\bA\.?I\.?\b|\bKI\b|künstliche intelligenz|artificial intelligence|machine learning|\bML\b|\bMLOps\b|\bLLMs?\b|gen(erative)? ?AI|"
                  r"deep learning|computer vision|\bNLP\b|data scien\w+|agentic|prompt engineer|neural|bildverarbeitung|maschinelles lernen)", re.I)
RELATED = re.compile(r"(data engineer\w*|data architect\w*|data platform|mlops|cloud (ai|ml)|analytics engineer|datenwissenschaft)", re.I)
# Not a full-time role: internships, working students, theses, apprenticeships, study programmes.
NONFT = re.compile(r"(intern\b|internship|praktik\w*|werkstudent\w*|working student|student(in)? ?\(|thesis|abschlussarbeit|masterarbeit|bachelorarbeit|"
                   r"ausbildung|duales? studium|dual(es)? study|trainee|apprentice)", re.I)


def build_regex(words):
    """Case-insensitive regex matching any of the plain words/phrases (escaped, whole-word); None if there are none."""
    parts = [re.escape(str(w).strip()) for w in (words or []) if str(w).strip()]
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.I) if parts else None


def load_overrides(path=OVERRIDE_PATH):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_overrides(core, related, nonft, data):
    """Defaults unless the user's file says otherwise. Returns (core, related, nonft)."""
    c = build_regex(data.get("core")) or core
    r = build_regex(data.get("related")) or related
    extra = build_regex(data.get("exclude"))
    n = re.compile(nonft.pattern + "|" + extra.pattern, re.I) if extra else nonft
    return c, r, n


CORE, RELATED, NONFT = apply_overrides(CORE, RELATED, NONFT, load_overrides())


def titles(text, rx, marker):
    """Cut a short segment around every match of rx (job lists are one run-on string). marker = regex of '(m/w/d)' style endings."""
    out = []
    marks = [m.end() for m in marker.finditer(text)]
    for m in rx.finditer(text):
        prev = max([e for e in marks if e <= m.start()] or [0])
        nxt = min([e for e in marks if e >= m.end()] or [len(text)])
        seg = text[max(prev, m.start() - 110):min(nxt + 1, m.end() + 90)]
        out.append(re.sub(r"\s+", " ", seg).strip(" -–|,")[:170])
    return out


def fulltime_ai_segments(text, marker):
    """AI-related segments of text that do not look like internships/theses/working-student roles."""
    return [s for s in set(titles(text, CORE, marker)) if not NONFT.search(s)]
