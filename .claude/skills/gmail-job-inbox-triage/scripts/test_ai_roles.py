"""Plain-script tests for the role-keyword override in ai_roles.py. Exits 1 on failure."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_roles as ar

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

C, R, N = ar.CORE, ar.RELATED, ar.NONFT
check("defaults match AI roles", bool(C.search("Machine Learning Engineer")), True)
check("no override file = defaults", ar.apply_overrides(C, R, N, {}), (C, R, N))
c, r, n = ar.apply_overrides(C, R, N, {"core": ["nurse", "ICU"], "related": ["care assistant"], "exclude": ["volunteer"]})
check("core replaced", (bool(c.search("Registered Nurse (m/f/d)")), bool(c.search("Machine Learning Engineer"))), (True, False))
check("whole words only", bool(c.search("nurseries")), False)
check("related replaced", bool(r.search("Care Assistant")), True)
check("exclude extends, defaults kept", (bool(n.search("volunteer role")), bool(n.search("Werkstudent AI"))), (True, True))
check("special characters are escaped", bool(ar.build_regex(["C++", "c#"]).search("Senior C++ Developer")), True)
check("empty list falls back to default", ar.apply_overrides(C, R, N, {"core": []})[0], C)
check("blank words ignored", ar.build_regex(["", "  "]), None)
check("missing file", ar.load_overrides("/nonexistent/x.json"), {})
import json, tempfile
f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); f.write("{broken"); f.close()
check("broken json = no override", ar.load_overrides(f.name), {})
f = open(f.name, "w"); f.write('["not", "a", "dict"]'); f.close()
check("non-dict json = no override", ar.load_overrides(f.name), {})
os.remove(f.name)
print("\n".join(fails) or "all passed")
sys.exit(1 if fails else 0)
