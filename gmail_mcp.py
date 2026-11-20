"""
Personal Gmail MCP server providing email management tools.

Provides search, list, read, send, label, and move operations for Gmail.
Connects via Claude Code MCP and uses OAuth2 authentication with
file-based token caching.

Usage: uv run --project . python gmail_mcp.py
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(PROJECT_ROOT, ".gmail-token.json")
CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, "gmail_credentials.json")

# If modifying these scopes, delete the token file.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------

_gmail: object | None = None
_gmail_lock = asyncio.Lock()


def _resolve_label_ids(client, names: list[str]) -> list[str]:
    """Map label names (case-insensitive, e.g. 'JobApplications/Rejected') to IDs.

    System labels (INBOX, TRASH, ...) and raw IDs pass through unchanged.
    """
    labels = client.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {l["name"].lower(): l["id"] for l in labels}
    by_id = {l["id"] for l in labels}
    ids = []
    for n in names:
        if n in by_id:
            ids.append(n)
        elif n.lower() in by_name:
            ids.append(by_name[n.lower()])
        else:
            raise ToolError(f"Unknown Gmail label '{n}'.")
    return ids


STATE_PATH = os.path.join(PROJECT_ROOT, ".gmail-auth-state.json")
REDIRECT_URI = "http://localhost:8765/"


def _make_flow():
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    flow.redirect_uri = REDIRECT_URI
    return flow


def _save_token(flow):
    creds = flow.credentials
    missing = [sc for sc in SCOPES if sc not in set(creds.scopes or [])]
    if missing:
        # Google's consent screen lets users untick individual permissions.
        print("\nWARNING: not all permissions were granted. Missing:\n  " + "\n  ".join(missing))
        print("Tools that need them (move/label/trash/send) will fail. Re-run the sign-in and "
              "tick ALL checkboxes on the consent screen.\n")
    with open(TOKEN_PATH, "w") as token:
        token.write(creds.to_json())
    return creds


def auth_url():
    """Step 1 of the two-step sign-in: print the URL and remember the PKCE state."""
    flow = _make_flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    with open(STATE_PATH, "w") as f:
        json.dump({"state": state, "code_verifier": flow.code_verifier}, f)
    print(url)


def auth_finish(redirected_url: str):
    """Step 2: exchange the pasted localhost URL for a token."""
    flow = _make_flow()
    saved = json.load(open(STATE_PATH))
    flow.code_verifier = saved["code_verifier"]
    flow.fetch_token(authorization_response=redirected_url.strip())
    _save_token(flow)
    os.remove(STATE_PATH)
    print(f"Saved token to {TOKEN_PATH}")


def _authorize_interactively():
    """One-time OAuth flow in a single terminal session: `python gmail_mcp.py --auth`.

    Copy-paste flow: works even when the browser can't reach localhost (WSL2).
    """
    flow = _make_flow()
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print(f"Open this URL in your browser:\n\n{url}\n")
    print("After approving, the browser shows 'localhost refused to connect'.")
    flow.fetch_token(authorization_response=input("Paste the full URL from the address bar here: ").strip())
    return _save_token(flow)


def _ensure_gmail_client():
    """Lazy initialization of the Gmail API client."""
    global _gmail
    if _gmail is not None:
        return _gmail

    # Load or obtain credentials
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Never block an MCP tool call on a browser flow; it just times out.
            raise ToolError(
                "Gmail is not authorized. In a terminal run: "
                ".venv/bin/python gmail_mcp.py --auth"
            )

        # Save the credentials for the next run
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    _gmail = build("gmail", "v1", credentials=creds)
    return _gmail


def _safe_get(msg: dict, *keys: str, name: str = None, default: str = "") -> str:
    """Safely navigate a Gmail message dict by key path.

    If `name` is provided, the last key in `keys` is expected to be a list of
    dicts, and the first dict whose `name` field matches `name` is returned.
    """
    d = msg
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        elif isinstance(d, list):
            # If we're at a list and have a name filter, find the matching item
            if name is not None:
                for item in d:
                    if isinstance(item, dict) and item.get("name") == name:
                        d = item.get("value", default)
                        return str(d) if d is not None else default
                return default
            return default
        else:
            return default

    # If name was provided but we didn't hit a list, return default
    if name is not None:
        return default

    return str(d) if d is not None else default


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("Gmail")


def _auth_required(tool_func):
    """Decorator to ensure Gmail client is initialized."""
    async def wrapper(*args, **kwargs):
        ctx: Context | None = kwargs.pop("ctx", None)
        await _ensure_gmail_client()
        return await tool_func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Tool: search_emails
# ---------------------------------------------------------------------------

@mcp.tool(
    name="search_emails",
    description="""
Search Gmail messages using Gmail search query syntax.

Examples:
  - "from:example@example.com subject:interview"
  - "label:jobs newer_than/7d"
  - "is:unread"

Parameters:
- query: Gmail search query string
- max_results: Maximum number of messages to return (default 20, max 500)
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def search_emails(
    query: Annotated[str, "Gmail search query syntax"],
    max_results: Annotated[int, "Maximum messages to return"] = 20,
    ctx: Context | None = None,
) -> ToolResult:
    """Search Gmail messages."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        result = await asyncio.to_thread(
            client.users().messages().list(userId="me", q=query, maxResults=max_results).execute
        )
        messages = result.get("messages", [])
    except HttpError as e:
        raise ToolError(f"Gmail API error: {e}")

    if not messages:
        return ToolResult(
            content=[{"type": "text", "text": "No messages found matching your query."}],
            structured_content={"messages": [], "query": query},
        )

    # Fetch full message details in batches
    msg_ids = [m["id"] for m in messages]
    results = []
    # Batch fetch (Gmail API limits to 100 per request, but we'll do sequential for simplicity)
    for msg_id in msg_ids[:max_results]:
        try:
            msg_detail = await asyncio.to_thread(
                client.users().messages().get(userId="me", id=msg_id, format="full").execute
            )
            results.append(msg_detail)
        except HttpError:
            continue

    # Format summary
    summaries = []
    for msg in results:
        headers = msg.get("payload", {}).get("headers", [])
        subject = next((_safe_get(h, "value") for h in headers if h.get("name") == "Subject"), "(no subject)")
        from_addr = next((_safe_get(h, "value") for h in headers if h.get("name") == "From"), "(unknown sender)")
        date = next((_safe_get(h, "value") for h in headers if h.get("name") == "Date"), "")
        labels = msg.get("labelIds", [])
        labels_str = ", ".join(labels) if labels else "none"

        summaries.append({
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "subject": subject,
            "from": from_addr,
            "date": date,
            "labels": labels_str,
        })

    return ToolResult(
        content=[{"type": "text", "text": f"Found {len(summaries)} messages matching your query."}],
        structured_content={"messages": summaries, "query": query},
    )


# ---------------------------------------------------------------------------
# Tool: list_emails
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_emails",
    description="""
List emails from your inbox or by label.

Parameters:
- label: Optional Gmail label name (e.g., 'INBOX', 'SENT', 'STARRED'). Defaults to INBOX.
- max_results: Maximum emails to return (default 20, max 500)
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def list_emails(
    label: Annotated[str, "Gmail label name (INBOX, SENT, STARRED, etc.)"] = "INBOX",
    max_results: Annotated[int, "Maximum emails to return"] = 20,
    ctx: Context | None = None,
) -> ToolResult:
    """List emails from a specific label/inbox."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        result = await asyncio.to_thread(
            client.users().messages().list(userId="me", labelIds=await asyncio.to_thread(_resolve_label_ids, client, [label]), maxResults=max_results).execute
        )
        messages = result.get("messages", [])
    except HttpError as e:
        raise ToolError(f"Gmail API error: {e}")

    if not messages:
        return ToolResult(
            content=[{"type": "text", "text": f"No messages found in label '{label}'."}],
            structured_content={"messages": [], "label": label},
        )

    msg_ids = [m["id"] for m in messages]
    summaries = []
    for msg_id in msg_ids:
        try:
            msg_detail = await asyncio.to_thread(
                client.users().messages().get(userId="me", id=msg_id, format="metadata", metadataHeaders=["Subject", "From", "Date"]).execute
            )
            headers = msg_detail.get("payload", {}).get("headers", [])
            subject = next((_safe_get(h, "value") for h in headers if h.get("name") == "Subject"), "(no subject)")
            from_addr = next((_safe_get(h, "value") for h in headers if h.get("name") == "From"), "(unknown sender)")
            date = next((_safe_get(h, "value") for h in headers if h.get("name") == "Date"), "")
            summaries.append({
                "id": msg_id,
                "subject": subject,
                "from": from_addr,
                "date": date,
            })
        except HttpError:
            continue

    return ToolResult(
        content=[{"type": "text", "text": f"Found {len(summaries)} emails in '{label}'."}],
        structured_content={"messages": summaries, "label": label},
    )


# ---------------------------------------------------------------------------
# Tool: get_email
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_email",
    description="""
Get full details of a specific Gmail message by ID.

Parameters:
- id: The Gmail message ID
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def get_email(
    id: Annotated[str, "Gmail message ID"],
    ctx: Context | None = None,
) -> ToolResult:
    """Get full email details by ID."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        msg = await asyncio.to_thread(
            client.users().messages().get(userId="me", id=id, format="full").execute
        )
    except HttpError as e:
        raise ToolError(f"Gmail API error: {e}")

    headers = msg.get("payload", {}).get("headers", [])
    subject = _safe_get(msg, "payload", "headers", name="Subject", default="")
    from_addr = _safe_get(msg, "payload", "headers", name="From", default="")
    date = _safe_get(msg, "payload", "headers", name="Date", default="")
    body = ""
    parts = msg.get("payload", {}).get("parts", [])
    if parts:
        for part in parts:
            if part.get("mimeType") == "text/plain":
                import base64
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
    else:
        # No parts — try raw
        import base64
        raw = msg.get("payload", {}).get("body", {}).get("data", "")
        if raw:
            body = base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")

    # Extract snippet if body is empty
    if not body:
        body = msg.get("snippet", "")

    return ToolResult(
        content=[{"type": "text", "text": f"Subject: {subject}\n\nFrom: {from_addr}\n\nDate: {date}\n\nBody:\n{body}"}],
        structured_content={
            "id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "subject": subject,
            "from": from_addr,
            "date": date,
            "body": body,
            "labels": msg.get("labelIds", []),
        },
    )


# ---------------------------------------------------------------------------
# Tool: send_email
# ---------------------------------------------------------------------------

@mcp.tool(
    name="send_email",
    description="""
Send a new email.

Parameters:
- to: Recipient email address
- subject: Email subject
- body: Email body text
- cc: Optional CC recipients (comma-separated)
- bcc: Optional BCC recipients (comma-separated)
""",
    annotations={"readOnlyHint": False},
    timeout=60.0,
)
async def send_email(
    to: Annotated[str, "Recipient email address"],
    subject: Annotated[str, "Email subject"],
    body: Annotated[str, "Email body text"],
    cc: Annotated[str | None, "CC recipients (comma-separated)"] = None,
    bcc: Annotated[str | None, "BCC recipients (comma-separated)"] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Send a new email."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        # Build the message
        import base64
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        # Send via Gmail API
        sent = await asyncio.to_thread(
            client.users().messages().send(userId="me", body={"raw": raw}).execute
        )

        return ToolResult(
            content=[{"type": "text", "text": f"Email sent to {to} with subject: {subject}"}],
            structured_content={
                "id": sent.get("id"),
                "to": to,
                "subject": subject,
                "message_id": sent.get("id"),
            },
        )
    except HttpError as e:
        raise ToolError(f"Failed to send email: {e}")
    except Exception as e:
        raise ToolError(f"Error sending email: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Tool: update_labels
# ---------------------------------------------------------------------------

@mcp.tool(
    name="update_labels",
    description="""
Add or remove labels from a Gmail message.

Parameters:
- id: Gmail message ID
- add_labels: Comma-separated list of label names to add (e.g., 'jobs', 'interviews')
- remove_labels: Comma-separated list of label names to remove (e.g., 'unread', 'important')
""",
    annotations={"readOnlyHint": False},
    timeout=30.0,
)
async def update_labels(
    id: Annotated[str, "Gmail message ID"],
    add_labels: Annotated[str | None, "Comma-separated label names to add"] = None,
    remove_labels: Annotated[str | None, "Comma-separated label names to remove"] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Add/remove labels from a Gmail message."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        label_ids = []
        if add_labels:
            for label_name in add_labels.split(","):
                label_name = label_name.strip()
                if label_name:
                    label_ids.append(label_name)
        if label_ids:
            label_ids = await asyncio.to_thread(_resolve_label_ids, client, label_ids)

        body = {}
        if label_ids:
            body["addLabelIds"] = label_ids
        if remove_labels:
            remove_list = [l.strip() for l in remove_labels.split(",") if l.strip()]
            if remove_list:
                body["removeLabelIds"] = await asyncio.to_thread(
                    _resolve_label_ids, client, remove_list
                )

        if not body:
            raise ToolError("No label changes specified.")

        await asyncio.to_thread(
            client.users().messages().modify(userId="me", id=id, body=body).execute
        )

        action = []
        if label_ids:
            action.append(f"added labels: {', '.join(label_ids)}")
        if remove_labels and remove_list:
            action.append(f"removed labels: {', '.join(remove_list)}")

        return ToolResult(
            content=[{"type": "text", "text": f"Updated labels for message {id}: {'; '.join(action)}"}],
            structured_content={
                "id": id,
                "added_labels": label_ids,
                "removed_labels": remove_labels.split(",") if remove_labels else [],
            },
        )
    except HttpError as e:
        raise ToolError(f"Gmail API error: {e}")


# ---------------------------------------------------------------------------
# Tool: move_email
# ---------------------------------------------------------------------------

@mcp.tool(
    name="move_email",
    description="""
Move an email to a different label/folder.

Parameters:
- id: Gmail message ID
- label: Target label name (e.g., 'jobs', 'archived', 'important')
""",
    annotations={"readOnlyHint": False},
    timeout=30.0,
)
async def move_email(
    id: Annotated[str, "Gmail message ID"],
    label: Annotated[str, "Target label name"],
    ctx: Context | None = None,
) -> ToolResult:
    """Move an email to a different label."""
    return await update_labels(id=id, add_labels=label, remove_labels="INBOX")


# ---------------------------------------------------------------------------
# Tool: trash_email
# ---------------------------------------------------------------------------

@mcp.tool(
    name="trash_email",
    description="""
Move an email to the trash.

Parameters:
- id: Gmail message ID
""",
    annotations={"readOnlyHint": False, "destructiveHint": True},
    timeout=30.0,
)
async def trash_email(
    id: Annotated[str, "Gmail message ID"],
    ctx: Context | None = None,
) -> ToolResult:
    """Move an email to trash."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        await asyncio.to_thread(
            client.users().messages().modify(userId="me", id=id, body={"addLabelIds": ["TRASH"]}).execute
        )
        return ToolResult(
            content=[{"type": "text", "text": f"Moved message {id} to trash."}],
            structured_content={"id": id, "action": "trash"},
        )
    except HttpError as e:
        raise ToolError(f"Failed to trash email: {e}")


# ---------------------------------------------------------------------------
# Tool: get_gmail_stats
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_gmail_stats",
    description="""
Get email statistics by label.

Parameters:
None
""",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    timeout=30.0,
)
async def get_gmail_stats(
    ctx: Context | None = None,
) -> ToolResult:
    """Get email statistics."""
    client = await asyncio.to_thread(_ensure_gmail_client)
    try:
        profile = await asyncio.to_thread(
            client.users().getProfile(userId="me").execute
        )
        total = profile.get("messagesTotal", 0)

        labels_result = await asyncio.to_thread(
            client.users().labels().list(userId="me").execute
        )
        label_counts = {}
        for label in labels_result.get("labels", []):
            detail = await asyncio.to_thread(
                client.users().labels().get(userId="me", id=label["id"]).execute
            )
            label_counts[label.get("name", "")] = detail.get("messagesTotal", 0)

        return ToolResult(
            content=[{"type": "text", "text": f"Total emails: {total}\n\nBy label:\n" + "\n".join(f"  {name}: {count}" for name, count in label_counts.items())}],
            structured_content={
                "total_emails": total,
                "label_counts": label_counts,
            },
        )
    except HttpError as e:
        raise ToolError(f"Gmail API error: {e}")


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--auth-url" in sys.argv:
        auth_url()
    elif "--auth-finish" in sys.argv:
        auth_finish(sys.argv[sys.argv.index("--auth-finish") + 1])
    elif "--auth" in sys.argv:
        _authorize_interactively()
        print(f"Saved token to {TOKEN_PATH}")
    else:
        mcp.run()