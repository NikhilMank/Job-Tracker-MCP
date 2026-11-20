---
name: gmail-mcp-troubleshooting
description: Diagnose and fix the local MCP servers in this project (jobtracker, gmail) — "tools fetch failed / Request timed out", Gmail calls hanging, OAuth login in WSL, Google 403 access_denied, localhost refused to connect, Gmail quota errors, label-name vs label-ID bugs. Use whenever an MCP server shows as failed, times out, or Gmail auth/tool calls misbehave.
---

# MCP server & Gmail troubleshooting (WSL2)

## 1. `claude mcp list` shows "Connected · tools fetch failed — Request timed out"
Cause is almost always **FastMCP 4.x**.
- `.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"` → must be `3.x`.
- Pin `fastmcp>=3.4.7,<4` in `pyproject.toml` **and** `requirements.txt`, then
  `uv pip install --python .venv/bin/python "fastmcp>=3.4.7,<4"`.
- Launch with the venv python in `.mcp.json` (`"command": ".venv/bin/python"`), **not** `uv run`:
  `uv run` re-syncs to the lock and silently brings 4.x back (and adds startup delay).
- Also: delete stale bytecode (`find . -name "*.pyc" -not -path "./.venv/*" -delete`); keep heavy
  imports lazy (Crawl4AI/Playwright); avoid lifespan for browser init.
- Reconnect with `/mcp` after any server-code change — the running process keeps the old code.

## 2. Gmail tool calls hang for 30 s then time out
No `.gmail-token.json` → the server tried the browser OAuth flow inside an MCP call. The server now
raises "Gmail is not authorized" immediately; fix by authorizing once (§3).

## 3. One-time authorization (copy-paste flow, works in WSL)
`.venv/bin/python gmail_mcp.py --auth` — run in a **normal terminal** (it waits for input; do not run
it through a tool with a timeout). Open the printed URL in the Windows browser, approve, then copy the
**full address-bar URL** of the failing `http://localhost:8765/?state=…&code=…` page and paste it
into the terminal. "localhost refused to connect" is expected and harmless; keep the same terminal
process running (the code is single-use and tied to it). The URL contains a one-time code — don't share it.

**Two-step mode (when the user pastes the URL in the chat instead of a terminal):** `.venv/bin/python gmail_mcp.py --auth-url` prints the
sign-in link and saves the PKCE state in `.gmail-auth-state.json`; after approval the user pastes the failing `http://localhost:8765/?state=…&code=…`
URL and you run `.venv/bin/python gmail_mcp.py --auth-finish "<that url>"`. The `state=` in the pasted URL must equal the one in the link you
gave (a URL from another sign-in attempt, e.g. an `--auth` still waiting in a terminal, cannot be used here - say so, don't try it). Start no
second sign-in in between: each new link invalidates the previous one. Check the result with the token's `scopes` (all three needed).

**Google `Error 403: access_denied` ("has not completed the Google verification process")**: the OAuth
app is in *Testing* mode. Cloud Console → *Google Auth Platform → Audience* (or *OAuth consent screen*)
→ *Test users* → add the exact Gmail address; ensure the Gmail API is enabled. On the warning screen
click *Advanced → Go to … (unsafe)*. Testing-mode refresh tokens expire after **7 days** → re-run `--auth`
weekly, or set publishing status to *In production* (stays unverified, still works for one user).

Files: `gmail_credentials.json` (client secret) and `.gmail-token.json` — both are in `.gitignore`;
never print their contents.

**"Request had insufficient authentication scopes" (403 on move/label/send/trash)**: the token was
granted fewer scopes than requested — Google's consent screen has per-permission checkboxes and
unticked ones are silently dropped. Check: `python3 -c "import json;print(json.load(open('.gmail-token.json'))['scopes'])"`
(needs `gmail.readonly`, `gmail.send`, `gmail.modify`). Fix: delete `.gmail-token.json`, re-run `--auth`, and
**tick every checkbox**. `--auth` now prints a WARNING when scopes are missing. Read-only calls keep working
with a read-only token, so this only shows up on the first write.

## 4. Gmail API gotchas fixed in `gmail_mcp.py` (keep them fixed)
- The API takes label **IDs** (`labelIds=`), not names; system labels (INBOX, SENT, TRASH) use the name as ID,
  user labels are `Label_123…`. `_resolve_label_ids()` maps names (case-insensitive,
  e.g. `JobApplications/Rejected`) to IDs for `list_emails`, `update_labels`, `move_email`.
- `list(…, maxResults=)` — there is no `max=`; `get_gmail_stats` uses `getProfile` + `labels().get(id)`.
- Search syntax for nested labels uses hyphens: `label:jobapplications-rejected`.
- Quota: *"Quota exceeded … Units per minute per user"* (HTTP 403). Don't loop one `messages.get` per mail;
  use batch requests of ~20–25, sleep ~3 s between batches, retry with backoff, persist progress
  (see `jobtracker-gmail-sync/scripts/fetch_gmail_label.py`). A burst of ~2,500 gets may lock you out for minutes.
- Scopes are readonly+send+modify; delete `.gmail-token.json` and re-auth after changing `SCOPES`.

## 5. Quick checks
- Handshake: `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' | timeout 5 .venv/bin/python main.py`
- After fixing: `claude mcp list` should show `✔ Connected` without "tools fetch failed".
- Deferred MCP tools may need `ToolSearch select:<name>` before first use in a session.

## Improving this skill
Add new symptoms/causes to the matching section as you meet them; keep the cause → fix pairs short.
