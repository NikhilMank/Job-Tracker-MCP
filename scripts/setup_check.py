#!/usr/bin/env python3
"""First-time setup check for JobTracker MCP. Read-only unless --apply (then it creates what is missing).

  .venv/bin/python scripts/setup_check.py                          # check everything, change nothing
  .venv/bin/python scripts/setup_check.py --prefix Jobs2026        # check labels under another parent label
  .venv/bin/python scripts/setup_check.py --no-gmail               # tracker only
  .venv/bin/python scripts/setup_check.py --gmail                  # force the Gmail checks (after the user said yes)
  .venv/bin/python scripts/setup_check.py --apply                  # also create the missing Gmail labels (and data/)

Checks: Python and FastMCP versions, installed packages, project MCP config, writable data folder, .gitignore
coverage of private files, and the Gmail credentials, token scopes and label structure. Gmail is optional: by default
the Gmail checks run only if the user wants Gmail (`gmail_enabled: yes` in data/routine-preferences.md) or, when that is
not decided yet, if Gmail files already exist. `gmail_enabled: no` skips them silently.
Never prints credentials, tokens or mail. Creating labels never touches existing mail. Exit code 1 if any check FAILs.
"""
import argparse, importlib.metadata as md, importlib.util, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
CHILD_LABELS = ["Rejected", "EasyApply", "Shortlisted", "NeedsAttention", "Attended"]
OPTIONAL_CHILD_LABELS = ["Accepted"]
GITIGNORE_NEEDS = ["*.db", "data/*", ".gmail-token.json", "gmail_credentials.json"]


def gmail_enabled_from_preferences(text):
    """True / False from a `- gmail_enabled: yes|no` line in data/routine-preferences.md, None if absent or '(not set)'."""
    for line in (text or "").splitlines():
        line = line.split("<!--")[0].strip().lstrip("-").strip().lower()
        if line.startswith("gmail_enabled:"):
            v = line.split(":", 1)[1].strip()
            return True if v.startswith("yes") else False if v.startswith("no") else None
    return None


def want_gmail(flag_gmail, flag_no_gmail, preference, files_exist):
    """Decide whether the Gmail checks run. Returns (run, reason)."""
    if flag_no_gmail:
        return False, "skipped (--no-gmail)"
    if flag_gmail:
        return True, ""
    if preference is False:
        return False, "skipped (you chose no Gmail: gmail_enabled is no)"
    if preference is True or files_exist:
        return True, ""
    return False, "not set up and not asked yet; it is optional (the first-time-setup skill asks)"


def required_labels(prefix, with_optional=False):
    """Parent first (Gmail nests by name, create the parent before its children)."""
    kids = CHILD_LABELS + (OPTIONAL_CHILD_LABELS if with_optional else [])
    return [prefix] + [f"{prefix}/{k}" for k in kids]


def missing_labels(existing_names, prefix, with_optional=False):
    have = {n.lower() for n in existing_names}
    return [n for n in required_labels(prefix, with_optional) if n.lower() not in have]


def missing_scopes(token_scopes):
    return [s for s in REQUIRED_SCOPES if s not in set(token_scopes or [])]


def fastmcp_ok(version):
    """Claude Code speaks MCP protocol 2024-11-05: FastMCP must be >=3.4.7 and <4."""
    try:
        parts = tuple(int(p) for p in version.split(".")[:3])
    except ValueError:
        return False
    return (3, 4, 7) <= parts < (4, 0, 0)


def create_labels(service, names):
    """Create labels in the given order; returns the names created."""
    created = []
    for n in names:
        service.users().labels().create(userId="me", body={
            "name": n, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).execute()
        created.append(n)
    return created


results = []  # (status, check, detail)
def report(status, check, detail=""):
    results.append((status, check, detail))
    print(f"[{status:<4}] {check}" + (f": {detail}" if detail else ""))


def check_environment(apply):
    v = sys.version_info
    report("OK" if v >= (3, 12) else "FAIL", "Python >= 3.12", f"{v.major}.{v.minor}.{v.micro}")
    in_venv = sys.prefix != sys.base_prefix
    venv_py = os.path.exists(os.path.join(ROOT, ".venv", "bin", "python"))
    report("OK" if venv_py else "FAIL", ".venv/bin/python exists", "" if venv_py else "create it: python3.12 -m venv .venv && pip install -r requirements.txt")
    if not in_venv:
        report("WARN", "running inside the project venv", "run this script with .venv/bin/python")
    try:
        fv = md.version("fastmcp")
        report("OK" if fastmcp_ok(fv) else "FAIL", "FastMCP >=3.4.7,<4", fv + ("" if fastmcp_ok(fv) else "  (fix: pip install 'fastmcp>=3.4.7,<4')"))
    except md.PackageNotFoundError:
        report("FAIL", "FastMCP installed", "pip install -r requirements.txt")
    for mod, why in (("aiosqlite", "tracker database"), ("crawl4ai", "scraping job URLs")):
        report("OK" if importlib.util.find_spec(mod) else "FAIL", f"package {mod}", why)
    pw = [p for p in (os.path.expanduser("~/.cache/ms-playwright"), os.path.expanduser("~/Library/Caches/ms-playwright")) if os.path.isdir(p)]
    report("OK" if pw else "WARN", "browser for scraping (Playwright)", "" if pw else "run crawl4ai-setup (only needed for add_job on URLs; add_job_from_text works without)")
    try:
        cfg = json.load(open(os.path.join(ROOT, ".mcp.json")))["mcpServers"]
        bad = [k for k, c in cfg.items() if c.get("command") != ".venv/bin/python"]
        report("OK" if "jobtracker" in cfg and not bad else "WARN", ".mcp.json registers jobtracker with .venv/bin/python",
               "" if not bad else f"not the venv python: {', '.join(bad)} (never use uv run)")
    except (OSError, ValueError, KeyError):
        report("FAIL", ".mcp.json readable", "start Claude Code from the repo folder")
    data = os.path.join(ROOT, "data")
    if not os.path.isdir(data) and apply:
        os.makedirs(data); report("DONE", "created data/")
    ok = os.path.isdir(data) and os.access(data, os.W_OK)
    report("OK" if ok else "TODO", "data/ folder writable", "" if ok else "re-run with --apply to create it")
    db = os.path.join(ROOT, "jobtracker.db")
    report("OK" if os.path.exists(db) else "INFO", "jobtracker.db", "exists" if os.path.exists(db) else "created automatically on the first add_job")
    try:
        gi = open(os.path.join(ROOT, ".gitignore")).read().split()
        miss = [g for g in GITIGNORE_NEEDS if g not in gi]
        report("OK" if not miss else "WARN", ".gitignore protects private files", "" if not miss else "missing: " + ", ".join(miss))
    except OSError:
        report("WARN", ".gitignore present")


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    token = os.path.join(ROOT, ".gmail-token.json")
    creds = Credentials.from_authorized_user_file(token)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def check_gmail(prefix, apply, with_optional):
    cred = os.path.join(ROOT, "gmail_credentials.json")
    tok = os.path.join(ROOT, ".gmail-token.json")
    report("OK" if os.path.exists(cred) else "TODO", "gmail_credentials.json (Google OAuth client)", "" if os.path.exists(cred) else "README, Setup > B, steps 1-4")
    if not os.path.exists(tok):
        report("TODO", ".gmail-token.json (signed in)", "run: .venv/bin/python gmail_mcp.py --auth (README, Setup > B, step 5)")
        return
    try:
        scopes = json.load(open(tok)).get("scopes")
    except (OSError, ValueError):
        report("FAIL", ".gmail-token.json readable", "delete it and run --auth again"); return
    ms = missing_scopes(scopes)
    if ms:
        report("FAIL", "token has all 3 Gmail permissions", "missing " + ", ".join(s.rsplit("/", 1)[-1] for s in ms) + "; delete the token, run --auth, tick every box")
        return
    report("OK", "token has all 3 Gmail permissions")
    try:
        svc = gmail_service()
        existing = [l["name"] for l in svc.users().labels().list(userId="me").execute().get("labels", [])]
    except Exception as e:  # network, expired token, API disabled
        report("FAIL", "Gmail API reachable", f"{type(e).__name__}: {str(e)[:120]} (token expired? run --auth again)"); return
    report("OK", "Gmail API reachable")
    miss = missing_labels(existing, prefix, with_optional)
    have = [n for n in required_labels(prefix, with_optional) if n not in miss]
    report("OK" if not miss else "TODO", f"labels under '{prefix}'", f"{len(have)} present" + (f", missing: {', '.join(miss)}" if miss else ""))
    if miss and apply:
        done = create_labels(svc, miss)
        report("DONE", "created labels", ", ".join(done))
    elif miss:
        print("       (dry run: re-run with --apply to create them)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default=os.environ.get("JOBTRACKER_LABEL_PREFIX", "JobApplications"), help="parent Gmail label")
    ap.add_argument("--no-gmail", action="store_true", help="skip the Gmail checks")
    ap.add_argument("--gmail", action="store_true", help="run the Gmail checks even if no preference is saved")
    ap.add_argument("--with-optional", action="store_true", help="also the optional 'Accepted' label")
    ap.add_argument("--apply", action="store_true", help="create missing labels / data folder")
    a = ap.parse_args()
    print(f"JobTracker setup check ({'APPLY' if a.apply else 'dry run'}), label prefix '{a.prefix}'\n")
    check_environment(a.apply)
    try:
        pref = gmail_enabled_from_preferences(open(os.path.join(ROOT, "data", "routine-preferences.md")).read())
    except OSError:
        pref = None
    files = os.path.exists(os.path.join(ROOT, ".gmail-token.json")) or os.path.exists(os.path.join(ROOT, "gmail_credentials.json"))
    run, why = want_gmail(a.gmail, a.no_gmail, pref, files)
    if not run:
        report("INFO", "Gmail", why)
    else:
        print()
        check_gmail(a.prefix, a.apply, a.with_optional)
    bad = [r for r in results if r[0] == "FAIL"]
    todo = [r for r in results if r[0] == "TODO"]
    print(f"\n{len([r for r in results if r[0] in ('OK','DONE')])} ok, {len(todo)} to do, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
