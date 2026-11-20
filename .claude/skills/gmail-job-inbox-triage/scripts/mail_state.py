#!/usr/bin/env python3
"""Remember when each mail task last ran, so the next run only reads NEWER mail (saves time, quota and tokens).

State file: data/job_mail_state.json
  {"tasks": {"<task>": {"last_run_start": <epoch>, "last_run_end": <epoch>, "pending_ids": ["..."]}}}

Rules that keep this safe (a watermark alone would silently drop mail that was deliberately left behind):
  * The watermark is the START time of the last completed run minus an overlap (default 1 h) -- mail that arrived
    while the run was in progress is never skipped; re-seeing a few mails is harmless.
  * `pending_ids` = mails the run left unresolved (needs-you, doubtful, candidates awaiting approval). They are
    re-included in the next run no matter how old they are; the caller drops those that are no longer in the inbox.
  * The state is only written by an explicit commit AFTER the run succeeded and was reported, never at the start.
  * No state yet (or --since all) -> fall back to a window of N days.

Library use:
    from mail_state import since_query, pending_ids, commit
    q_part, started = since_query("job_inbox_triage", default_days=30)    # -> "after:1759650000", epoch
    ...run...
    commit("job_inbox_triage", started, pending=[...ids...])
CLI:  mail_state.py show | reset <task>
"""
import json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
STATE_PATH = os.path.join(ROOT, "data", "job_mail_state.json")
OVERLAP_S = 3600


def _load():
    try:
        return json.load(open(STATE_PATH))
    except (OSError, ValueError):
        return {"tasks": {}}


def since_query(task: str, default_days: int = 30, mode: str = "auto"):
    """Return (gmail query fragment, start_epoch). mode: 'auto' (use state), 'all' (no time limit, ignore state), or an int = days."""
    started = int(time.time())
    if mode == "all":  # first-time full sweep: no time constraint at all, state ignored
        return "", started
    if str(mode).isdigit():
        return f"newer_than:{int(mode)}d", started
    last = _load()["tasks"].get(task, {}).get("last_run_start") if mode == "auto" else None
    if last:
        return f"after:{int(last) - OVERLAP_S}", started
    return f"newer_than:{default_days}d", started


def pending_ids(task: str):
    return list(_load()["tasks"].get(task, {}).get("pending_ids", []))


def commit(task: str, started: int, pending=None):
    state = _load()
    state["tasks"][task] = {"last_run_start": int(started), "last_run_end": int(time.time()),
                            "last_run_human": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
                            "pending_ids": sorted(set(pending or []))}
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    json.dump(state, open(STATE_PATH, "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "show":
        print(json.dumps(_load(), indent=1))
    elif cmd == "reset" and len(sys.argv) > 2:
        st = _load(); st["tasks"].pop(sys.argv[2], None); json.dump(st, open(STATE_PATH, "w"), indent=1); print("reset", sys.argv[2])
    else:
        sys.exit(__doc__)
