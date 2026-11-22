"""Shared user configuration for the Gmail scripts (stdlib only, safe to import anywhere).

The parent Gmail label is resolved in this order: JOBTRACKER_LABEL_PREFIX env var, then `label_prefix` in the git-ignored
data/routine-preferences.md (saved by the first-time-setup skill), then the default. Keeping this in one place means a custom
label name chosen at setup is honoured by every script and survives updates.
"""
import os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PREFIX = "JobApplications"


def saved_label_prefix(path=None):
    path = path or os.path.join(ROOT, "data", "routine-preferences.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    m = re.search(r"^\s*-\s*label_prefix\s*:\s*([^<\n]*)", text, re.M)
    v = m.group(1).strip() if m else ""
    return "" if v in ("", "(not set)") else v


def label_prefix(path=None):
    return os.environ.get("JOBTRACKER_LABEL_PREFIX") or saved_label_prefix(path) or DEFAULT_PREFIX
