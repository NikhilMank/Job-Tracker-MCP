#!/usr/bin/env python3
"""First-time setup check for JobTracker MCP. Read-only unless --apply (then it creates what is missing).

  .venv/bin/python scripts/setup_check.py                          # check everything, change nothing
  .venv/bin/python scripts/setup_check.py --prefix Jobs2026        # check labels under another parent label
  .venv/bin/python scripts/setup_check.py --no-gmail               # tracker only
  .venv/bin/python scripts/setup_check.py --gmail                  # force the Gmail checks (after the user said yes)
  .venv/bin/python scripts/setup_check.py --labels rejected,shortlisted --apply   # create exactly these labels (and data/)
  .venv/bin/python scripts/setup_check.py --labels all             # check every label this project can use

Checks: Python and FastMCP versions, installed packages, project MCP config, writable data folder, .gitignore
coverage of private files, and the Gmail credentials, token scopes and label structure. Gmail is optional: by default
the Gmail checks run only if the user wants Gmail (`gmail_enabled: yes` in data/routine-preferences.md) or, when that is
not decided yet, if Gmail files already exist. `gmail_enabled: no` skips them silently.

Labels are opt-in too: each one belongs to a feature, and only the labels the user chose are checked or created. The choice
comes from data/routine-preferences.md (file_receipts, file_rejections, label_easyapply, label_shortlisted,
label_needs_attention, label_attended, label_accepted) or from --labels. No choice yet means no label is touched.
Never prints credentials, tokens or mail. Creating labels never touches existing mail. Exit code 1 if any check FAILs.
"""
import argparse, importlib.metadata as md, importlib.util, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
# label key -> suffix under the parent label ("" = the parent itself, used for filed application receipts)
LABEL_SUFFIX = {"receipts": "", "rejected": "/Rejected", "easyapply": "/EasyApply", "shortlisted": "/Shortlisted",
                "needs_attention": "/NeedsAttention", "attended": "/Attended", "accepted": "/Accepted"}
# preference key (data/routine-preferences.md) -> label it needs
LABEL_PREFS = {"file_receipts": "receipts", "file_rejections": "rejected", "label_easyapply": "easyapply",
               "label_shortlisted": "shortlisted", "label_needs_attention": "needs_attention",
               "label_attended": "attended", "label_accepted": "accepted"}
GITIGNORE_NEEDS = ["*.db", "data/*", ".gmail-token.json", "gmail_credentials.json"]


def preference(text, key):
    """True / False from a `- key: yes|no` line in data/routine-preferences.md, None if absent or '(not set)'."""
    for line in (text or "").splitlines():
        line = line.split("<!--")[0].strip().lstrip("-").strip().lower()
        if line.startswith(key + ":"):
            v = line.split(":", 1)[1].strip()
            return True if v.startswith("yes") else False if v.startswith("no") else None
    return None


def gmail_enabled_from_preferences(text):
    return preference(text, "gmail_enabled")


def wanted_label_keys(text):
    """Label keys the user chose, in LABEL_SUFFIX order. None if they have not answered any label question yet."""
    answers = {k: preference(text, p) for p, k in LABEL_PREFS.items()}
    if all(v is None for v in answers.values()):
        return None
    return [k for k in LABEL_SUFFIX if answers.get(k)]


PREFS_PATH = os.path.join("data", "routine-preferences.md")
PREFS_TEMPLATE = os.path.join(".claude", "skills", "daily-job-routine", "routine-preferences.template.md")


def preference_keys(text):
    """{key: value} for every `- key: value` line (comments after <!-- stripped). Value '' when empty."""
    out = {}
    for line in (text or "").splitlines():
        line = line.split("<!--")[0].strip()
        if line.startswith("- ") and ":" in line:
            k, v = line[2:].split(":", 1)
            out[k.strip()] = v.strip()
    return out


def unanswered_preferences(template_text, prefs_text):
    """Keys the template has that the user's file lacks or leaves '(not set)'. After an update this lists the NEW questions.
    Mail-related keys are ignored when the user turned Gmail off."""
    tmpl, mine = preference_keys(template_text), preference_keys(prefs_text)
    gmail_off = preference(prefs_text, "gmail_enabled") is False
    return [k for k in tmpl if (k not in mine or mine[k] in ("", "(not set)")) and not (gmail_off and k != "gmail_enabled")]


MIGRATIONS_PATH = os.path.join(".claude", "skills", "daily-job-routine", "preferences-migrations.json")


def preferences_version(text):
    """Format version recorded in the user's file; 1 when absent (files written before versioning)."""
    v = preference_keys(text).get("preferences_version", "")
    return int(v) if v.isdigit() else 1


def pending_migrations(migrations, from_v, to_v):
    return sorted([m for m in migrations or [] if from_v < int(m.get("version", 0)) <= to_v], key=lambda m: int(m["version"]))


def migrate_preferences(text, migrations, to_v):
    """Apply renames in order, keep every value and comment, note removed keys, bump preferences_version.
    Returns (new_text, actions). Never drops an answer."""
    actions, new = [], text
    for m in pending_migrations(migrations, preferences_version(text), to_v):
        for old, newk in (m.get("renamed") or {}).items():
            pat = re.compile(r"^(\s*-\s*)" + re.escape(old) + r"(\s*:)", re.M)
            if pat.search(new) and not re.search(r"^\s*-\s*" + re.escape(newk) + r"\s*:", new, re.M):
                new = pat.sub(lambda mo: mo.group(1) + newk + mo.group(2), new, count=1)
                actions.append(f"renamed {old} -> {newk} (your value kept)")
        for gone in m.get("removed") or []:
            if re.search(r"^\s*-\s*" + re.escape(gone) + r"\s*:", new, re.M):
                actions.append(f"{gone} is no longer used (left in your file, ignored)")
    line = f"- preferences_version: {to_v}"
    if re.search(r"^\s*-\s*preferences_version\s*:.*$", new, re.M):
        new = re.sub(r"^\s*-\s*preferences_version\s*:.*$", line, new, count=1, flags=re.M)
    elif "## Setup" in new:
        new = new.replace("## Setup\n", "## Setup\n" + line + "\n", 1)
    else:
        new = line + "\n" + new
    return new, actions


def resolve_prefix(cli, env, prefs_text, default="JobApplications"):
    """Parent Gmail label: --prefix, then JOBTRACKER_LABEL_PREFIX, then label_prefix in the saved preferences, then the default."""
    saved = preference_keys(prefs_text).get("label_prefix", "")
    saved = "" if saved in ("", "(not set)") else saved
    return cli or env or saved or default


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


def required_labels(prefix, keys):
    """Label names for the chosen keys, parent first (Gmail nests by name; create the parent before its children).
    Choosing any label creates the parent; nothing chosen means nothing is required."""
    keys = [k for k in LABEL_SUFFIX if k in set(keys or [])]
    if not keys:
        return []
    return [prefix] + [prefix + LABEL_SUFFIX[k] for k in keys if k != "receipts"]


def missing_labels(existing_names, prefix, keys):
    have = {n.lower() for n in existing_names}
    return [n for n in required_labels(prefix, keys) if n.lower() not in have]


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


def check_gmail(prefix, apply, keys):
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
    if keys is None:
        report("INFO", "labels", "not chosen yet; each label is optional (the first-time-setup skill asks which you want)")
        return
    if not keys:
        report("INFO", "labels", "you chose none: nothing to create")
        return
    miss = missing_labels(existing, prefix, keys)
    have = [n for n in required_labels(prefix, keys) if n not in miss]
    report("OK" if not miss else "TODO", f"labels under '{prefix}'", f"{len(have)} present" + (f", missing: {', '.join(miss)}" if miss else ""))
    if miss and apply:
        done = create_labels(svc, miss)
        report("DONE", "created labels", ", ".join(done))
    elif miss:
        print("       (dry run: re-run with --apply to create them)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default=None, help="parent Gmail label (default: JOBTRACKER_LABEL_PREFIX, then label_prefix in your saved preferences, then JobApplications)")
    ap.add_argument("--no-gmail", action="store_true", help="skip the Gmail checks")
    ap.add_argument("--gmail", action="store_true", help="run the Gmail checks even if no preference is saved")
    ap.add_argument("--labels", help="comma separated label keys to check/create, or 'all' (default: your saved choice). Keys: " + ", ".join(LABEL_SUFFIX))
    ap.add_argument("--apply", action="store_true", help="create missing labels / data folder and migrate the preferences file")
    a = ap.parse_args()
    try:
        prefs_text = open(os.path.join(ROOT, PREFS_PATH), encoding="utf-8").read()
    except OSError:
        prefs_text = None
    prefix = resolve_prefix(a.prefix, os.environ.get("JOBTRACKER_LABEL_PREFIX"), prefs_text)
    print(f"JobTracker setup check ({'APPLY' if a.apply else 'dry run'}), label prefix '{prefix}'\n")
    check_environment(a.apply)
    prefs_text = check_preferences(prefs_text, a.apply)
    pref = gmail_enabled_from_preferences(prefs_text)
    files = os.path.exists(os.path.join(ROOT, ".gmail-token.json")) or os.path.exists(os.path.join(ROOT, "gmail_credentials.json"))
    run, why = want_gmail(a.gmail, a.no_gmail, pref, files)
    if not run:
        report("INFO", "Gmail", why)
    else:
        print()
        if a.labels:
            keys = list(LABEL_SUFFIX) if a.labels.strip() == "all" else [k.strip() for k in a.labels.split(",") if k.strip()]
            bad_keys = [k for k in keys if k not in LABEL_SUFFIX]
            if bad_keys:
                sys.exit(f"unknown label key(s): {', '.join(bad_keys)}; valid: {', '.join(LABEL_SUFFIX)}")
        else:
            keys = wanted_label_keys(prefs_text)
        check_gmail(prefix, a.apply, keys)
    bad = [r for r in results if r[0] == "FAIL"]
    todo = [r for r in results if r[0] == "TODO"]
    print(f"\n{len([r for r in results if r[0] in ('OK','DONE')])} ok, {len(todo)} to do, {len(bad)} failed")
    sys.exit(1 if bad else 0)


def check_preferences(prefs_text, apply):
    """Report on data/routine-preferences.md: format migrations, then unanswered (new) questions. Returns the (possibly migrated) text."""
    if prefs_text is None:
        report("INFO", "preferences", "not saved yet; the first-time-setup skill asks and saves them")
        return ""
    try:
        template = open(os.path.join(ROOT, PREFS_TEMPLATE), encoding="utf-8").read()
        migrations = json.load(open(os.path.join(ROOT, MIGRATIONS_PATH), encoding="utf-8"))
    except (OSError, ValueError):
        return prefs_text
    mine, theirs = preferences_version(prefs_text), preferences_version(template)
    if mine < theirs:
        new_text, actions = migrate_preferences(prefs_text, migrations, theirs)
        detail = f"format v{mine} -> v{theirs}: " + ("; ".join(actions) if actions else "no key changes")
        if apply:
            path = os.path.join(ROOT, PREFS_PATH)
            open(path + f".bak-v{mine}", "w", encoding="utf-8").write(prefs_text)
            open(path, "w", encoding="utf-8").write(new_text)
            report("DONE", "preferences migrated", detail + f" (copy of the old file: {PREFS_PATH}.bak-v{mine})")
            prefs_text = new_text
        else:
            report("TODO", "preferences need a format migration", detail + " (re-run with --apply; a copy of your file is kept)")
    todo = unanswered_preferences(template, prefs_text)
    report("OK" if not todo else "TODO", "preferences answered", "" if not todo else "not answered yet: " + ", ".join(todo) + " (say \"check my setup\" and I ask only these)")
    return prefs_text


if __name__ == "__main__":
    main()
