"""Plain-script test for jobtracker_config.label_prefix. Exits 1 on failure."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobtracker_config as c

fails = []
def check(n, got, want):
    if got != want: fails.append(f"{n}: got {got!r}, want {want!r}")

def prefs(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False); f.write(text); f.close(); return f.name
os.environ.pop("JOBTRACKER_LABEL_PREFIX", None)
check("default", c.label_prefix("/nonexistent"), "JobApplications")
check("saved", c.label_prefix(prefs("- label_prefix: Jobs2026  <!-- x -->\n")), "Jobs2026")
check("(not set) ignored", c.label_prefix(prefs("- label_prefix: (not set)\n")), "JobApplications")
os.environ["JOBTRACKER_LABEL_PREFIX"] = "FromEnv"
check("env wins", c.label_prefix(prefs("- label_prefix: Jobs2026\n")), "FromEnv")
print("\n".join(fails) or "all passed"); sys.exit(1 if fails else 0)
