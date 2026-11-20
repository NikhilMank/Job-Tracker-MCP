"""Shared AI-role detection for job-letter and job-suggestion mail (used by scan_company_jobletters.py and clean_job_suggestions.py)."""
import re

CORE = re.compile(r"(\bA\.?I\.?\b|\bKI\b|künstliche intelligenz|artificial intelligence|machine learning|\bML\b|\bMLOps\b|\bLLMs?\b|gen(erative)? ?AI|"
                  r"deep learning|computer vision|\bNLP\b|data scien\w+|agentic|prompt engineer|neural|bildverarbeitung|maschinelles lernen)", re.I)
RELATED = re.compile(r"(data engineer\w*|data architect\w*|data platform|mlops|cloud (ai|ml)|analytics engineer|datenwissenschaft)", re.I)
# Not a full-time role: internships, working students, theses, apprenticeships, study programmes.
NONFT = re.compile(r"(intern\b|internship|praktik\w*|werkstudent\w*|working student|student(in)? ?\(|thesis|abschlussarbeit|masterarbeit|bachelorarbeit|"
                   r"ausbildung|duales? studium|dual(es)? study|trainee|apprentice)", re.I)


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
