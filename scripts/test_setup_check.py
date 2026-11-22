"""Plain-script tests for the pure logic in setup_check.py (no network, no Gmail). Exits 1 on failure."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup_check as sc

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

check("labels, parent first", sc.required_labels("JA")[:2], ["JA", "JA/Rejected"])
check("label count", len(sc.required_labels("JA")), 6)
check("optional label", sc.required_labels("JA", True)[-1], "JA/Accepted")
check("nothing missing", sc.missing_labels(sc.required_labels("JA"), "JA"), [])
check("case-insensitive", sc.missing_labels([n.lower() for n in sc.required_labels("JA")], "JA"), [])
check("all missing keeps order", sc.missing_labels(["INBOX"], "JA"), sc.required_labels("JA"))
check("only children missing", sc.missing_labels(["JA", "JA/Rejected"], "JA"), ["JA/EasyApply", "JA/Shortlisted", "JA/NeedsAttention", "JA/Attended"])
check("custom prefix", sc.missing_labels(["JobApplications"], "Jobs 2026")[0], "Jobs 2026")
check("scopes ok", sc.missing_scopes(sc.REQUIRED_SCOPES), [])
check("scopes missing modify", [s.rsplit("/", 1)[-1] for s in sc.missing_scopes(sc.REQUIRED_SCOPES[:2])], ["gmail.modify"])
check("scopes none", len(sc.missing_scopes(None)), 3)
check("fastmcp 3.4.7", sc.fastmcp_ok("3.4.7"), True)
check("fastmcp 3.9.0", sc.fastmcp_ok("3.9.0"), True)
check("fastmcp 4.0.0 rejected", sc.fastmcp_ok("4.0.0"), False)
check("fastmcp 3.4.6 rejected", sc.fastmcp_ok("3.4.6"), False)
check("fastmcp garbage", sc.fastmcp_ok("abc"), False)

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
