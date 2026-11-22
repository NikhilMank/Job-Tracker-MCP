"""Plain-script tests for the pure logic in setup_check.py (no network, no Gmail). Exits 1 on failure."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup_check as sc

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

ALL = list(sc.LABEL_SUFFIX)
check("nothing chosen, nothing required", sc.required_labels("JA", []), [])
check("none keys", sc.required_labels("JA", None), [])
check("only rejected: parent + child", sc.required_labels("JA", ["rejected"]), ["JA", "JA/Rejected"])
check("receipts only: just the parent", sc.required_labels("JA", ["receipts"]), ["JA"])
check("order is stable, parent first", sc.required_labels("JA", ["attended", "rejected", "receipts"]), ["JA", "JA/Rejected", "JA/Attended"])
check("all labels", len(sc.required_labels("JA", ALL)), 7)
check("unknown key ignored", sc.required_labels("JA", ["bogus"]), [])
check("nothing missing", sc.missing_labels(sc.required_labels("JA", ALL), "JA", ALL), [])
check("case-insensitive", sc.missing_labels([n.lower() for n in sc.required_labels("JA", ALL)], "JA", ALL), [])
check("only unchosen labels are not reported", sc.missing_labels(["JA"], "JA", ["rejected"]), ["JA/Rejected"])
check("custom prefix", sc.missing_labels(["JobApplications"], "Jobs 2026", ["shortlisted"])[0], "Jobs 2026")
P = "- file_receipts: yes\n- file_rejections: no\n- label_shortlisted: yes   <!-- x -->\n- label_needs_attention: (not set)\n"
check("wanted from prefs", sc.wanted_label_keys(P), ["receipts", "shortlisted"])
check("wanted: all unanswered = undecided", sc.wanted_label_keys("- file_receipts: (not set)\n- label_attended: (not set)"), None)
check("wanted: empty text = undecided", sc.wanted_label_keys(""), None)
check("wanted: all no = none chosen", sc.wanted_label_keys("- file_receipts: no\n- file_rejections: no"), [])
check("preference parser", (sc.preference("- file_receipts: yes", "file_receipts"), sc.preference("- x: no", "x"), sc.preference("- x: ask", "x")), (True, False, None))
check("scopes ok", sc.missing_scopes(sc.REQUIRED_SCOPES), [])
check("scopes missing modify", [s.rsplit("/", 1)[-1] for s in sc.missing_scopes(sc.REQUIRED_SCOPES[:2])], ["gmail.modify"])
check("scopes none", len(sc.missing_scopes(None)), 3)
check("fastmcp 3.4.7", sc.fastmcp_ok("3.4.7"), True)
check("fastmcp 3.9.0", sc.fastmcp_ok("3.9.0"), True)
check("fastmcp 4.0.0 rejected", sc.fastmcp_ok("4.0.0"), False)
check("fastmcp 3.4.6 rejected", sc.fastmcp_ok("3.4.6"), False)
check("fastmcp garbage", sc.fastmcp_ok("abc"), False)

check("pref yes", sc.gmail_enabled_from_preferences("## Setup\n- gmail_enabled: yes   <!-- x -->\n"), True)
check("pref no", sc.gmail_enabled_from_preferences("- gmail_enabled: no\n"), False)
check("pref not set", sc.gmail_enabled_from_preferences("- gmail_enabled: (not set)  <!-- yes | no -->\n"), None)
check("pref absent", sc.gmail_enabled_from_preferences("# nothing"), None)
check("pref none text", sc.gmail_enabled_from_preferences(None), None)
check("gmail: no skips even with files", sc.want_gmail(False, False, False, True)[0], False)
check("gmail: yes runs", sc.want_gmail(False, False, True, False)[0], True)
check("gmail: undecided without files skips", sc.want_gmail(False, False, None, False)[0], False)
check("gmail: undecided with files runs", sc.want_gmail(False, False, None, True)[0], True)
check("--gmail forces over a no", sc.want_gmail(True, False, False, False)[0], True)
check("--no-gmail wins", sc.want_gmail(True, True, True, True)[0], False)

T = "- gmail_enabled: (not set)\n- job_alerts: (not set) <!-- x -->\n- file_receipts: (not set)\n- new_key: (not set)\n"
check("all answered", sc.unanswered_preferences(T, "- gmail_enabled: yes\n- job_alerts: leave\n- file_receipts: no\n- new_key: yes\n"), [])
check("new template key = new question", sc.unanswered_preferences(T, "- gmail_enabled: yes\n- job_alerts: leave\n- file_receipts: no\n"), ["new_key"])
check("(not set) is unanswered", sc.unanswered_preferences(T, "- gmail_enabled: yes\n- job_alerts: (not set)\n- file_receipts: no\n- new_key: no\n"), ["job_alerts"])
check("gmail off ignores mail keys", sc.unanswered_preferences(T, "- gmail_enabled: no\n"), [])
check("gmail undecided lists the unanswered rest", sc.unanswered_preferences(T, "- job_alerts: leave\n"), ["gmail_enabled", "file_receipts", "new_key"])
check("existing answers never listed", sc.preference_keys("- a: yes <!-- c -->\n## h\n- b: \n")["a"], "yes")

M = [{"version": 2, "renamed": {"old_key": "new_key"}, "removed": ["gone"]}, {"version": 3, "renamed": {"new_key": "newer_key"}}]
old = "# my notes\n## Setup\n- gmail_enabled: yes\n- old_key: trash-all  <!-- c -->\n- gone: yes\n"
check("version defaults to 1", sc.preferences_version(old), 1)
check("pending", [m["version"] for m in sc.pending_migrations(M, 1, 2)], [2])
new, acts = sc.migrate_preferences(old, M, 3)
check("rename chain keeps value", "- newer_key: trash-all  <!-- c -->" in new and "old_key" not in new, True)
check("version recorded", sc.preferences_version(new), 3)
check("notes kept", new.startswith("# my notes"), True)
check("removed key reported not deleted", ("- gone: yes" in new, any("gone" in a for a in acts)), (True, True))
again, acts2 = sc.migrate_preferences(new, M, 3)
check("idempotent", (again, acts2), (new, []))
check("rename never overwrites an existing new key", "old_key" in sc.migrate_preferences("- old_key: a\n- new_key: b\n", M[:1], 2)[0], True)
check("prefix: cli wins", sc.resolve_prefix("A", "B", "- label_prefix: C\n"), "A")
check("prefix: env then saved", (sc.resolve_prefix(None, "B", "- label_prefix: C\n"), sc.resolve_prefix(None, None, "- label_prefix: C\n")), ("B", "C"))
check("prefix: unset falls to default", sc.resolve_prefix(None, None, "- label_prefix: (not set)\n"), "JobApplications")

class _Req:
    def __init__(s, log, body): s.log, s.body = log, body
    def execute(s): s.log.append(s.body["name"]); return {}
class _Labels:
    def __init__(s, log): s.log = log
    def create(s, userId, body): return _Req(s.log, body)
class _Users:
    def __init__(s, log): s.log = log
    def labels(s): return _Labels(s.log)
class _Svc:
    def __init__(s): s.log = []
    def users(s): return _Users(s.log)
svc = _Svc()
check("create_labels returns names in order", sc.create_labels(svc, ["JA", "JA/Rejected"]), ["JA", "JA/Rejected"])
check("create_labels called API in order", svc.log, ["JA", "JA/Rejected"])

print("\n".join(fails) or "all passed")
sys.exit(1 if fails else 0)
