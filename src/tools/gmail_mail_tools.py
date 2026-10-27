"""Reading, drafting and sending Gmail.

Sending always takes two steps. The model writes a draft, which the user can also see in Gmail's
Drafts. gmail_send_draft then previews it and only sends on a second call after the user agrees
(utils/send_guard.py). No tool sends mail in one go.
"""
import base64
from email.message import EmailMessage

from fastmcp.exceptions import ToolError

from clients.gmail_client import gmail_client
from constants.tool_annotations import READ, SEND, WRITE
from server import google_mcp
from tools.gmail_tools import _fetch_headers, _require_query
from utils.gmail_parser import _attachments, _body_text, _header
from utils.send_guard import send_guard

MAX_LIST = 100
LIST_HEADERS = ["From", "To", "Subject", "Date"]
REPLY_HEADERS = ["From", "Reply-To", "Subject", "Message-ID", "References"]


def _summary(m: dict) -> dict:
    return {
        "id": m["id"],
        "thread_id": m.get("threadId"),
        "from": _header(m, "From"),
        "to": _header(m, "To"),
        "subject": _header(m, "Subject"),
        "date": _header(m, "Date"),
        "snippet": m.get("snippet"),
        "unread": "UNREAD" in m.get("labelIds", []),
    }


def _draft_details(draft_id: str) -> dict:
    """Everything that would go out, read back from Gmail so the preview matches what is sent."""
    m = gmail_client.get_draft(draft_id, format="full")["message"]
    return {
        "draft_id": draft_id,
        "to": _header(m, "To"),
        "cc": _header(m, "Cc"),
        "bcc": _header(m, "Bcc"),
        "subject": _header(m, "Subject"),
        "body": _body_text(m.get("payload", {})),
        "attachments": _attachments(m.get("payload", {})),
    }


@google_mcp.tool(annotations=READ)
def gmail_search_messages(query: str = "in:inbox is:unread", max_results: int = 20) -> dict:
    """Find emails with a Gmail search query, newest first: sender, subject, date and a snippet.

    Uses Gmail search syntax, e.g. "from:anna@example.com", "subject:invoice newer_than:30d",
    "is:starred", "has:attachment". Use gmail_get_message to read one in full."""
    query = _require_query(query)
    found = gmail_client.list_messages(q=query, maxResults=max(1, min(max_results, MAX_LIST)), fields="messages/id,resultSizeEstimate")
    ids = [m["id"] for m in found.get("messages", [])]
    return {
        "query": query,
        "estimated_matches": found.get("resultSizeEstimate", len(ids)),
        "messages": [_summary(m) for m in _fetch_headers(ids, LIST_HEADERS)],
    }


@google_mcp.tool(annotations=READ)
def gmail_get_message(message_id: str, max_chars: int = 20000) -> dict:
    """Read one email in full: headers, the text of the body (HTML is converted to text) and the
    names of its attachments."""
    m = gmail_client.get_message(message_id, format="full")
    body = _body_text(m.get("payload", {}))
    return {
        **_summary(m),
        "cc": _header(m, "Cc"),
        "body": body[:max_chars],
        "truncated": len(body) > max_chars,
        "attachments": _attachments(m.get("payload", {})),
    }


@google_mcp.tool(annotations=READ)
def gmail_list_drafts(max_results: int = 20) -> dict:
    """The user's Gmail drafts, newest first, with the draft_id that gmail_send_draft needs."""
    drafts = gmail_client.list_drafts(maxResults=max(1, min(max_results, MAX_LIST))).get("drafts", [])
    draft_ids = {d["message"]["id"]: d["id"] for d in drafts}
    messages = _fetch_headers(list(draft_ids), LIST_HEADERS)
    return {"drafts": [{"draft_id": draft_ids[m["id"]], **_summary(m)} for m in messages]}


@google_mcp.tool(annotations=WRITE)
def gmail_create_draft(
    to: list[str] | None = None,
    subject: str = "",
    body: str = "",
    cc: list[str] | None = None,
    reply_to_message_id: str | None = None,
) -> dict:
    """Write an email as a draft in the user's Gmail. Nothing is sent.

    To reply, pass reply_to_message_id: the draft joins that conversation, and `to` and `subject`
    default to the sender and "Re: <subject>". Show the user the draft, then use gmail_send_draft
    if they want it sent."""
    msg = EmailMessage()
    thread_id = None
    if reply_to_message_id:
        original = gmail_client.get_message(reply_to_message_id, format="metadata", metadataHeaders=REPLY_HEADERS)
        thread_id = original.get("threadId")
        if message_id := _header(original, "Message-ID"):
            msg["In-Reply-To"] = message_id
            msg["References"] = f"{_header(original, 'References') or ''} {message_id}".strip()
        to = to or [_header(original, "Reply-To") or _header(original, "From")]
        original_subject = _header(original, "Subject") or ""
        subject = subject or (original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}")
    if not to:
        raise ToolError("Give at least one recipient in `to`")

    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.set_content(body)
    message = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    if thread_id:
        message["threadId"] = thread_id
    draft = gmail_client.create_draft({"message": message})
    return {
        "draft_id": draft["id"],
        "to": to,
        "cc": cc or [],
        "subject": subject,
        "next": "Saved in the user's Gmail Drafts. To send it, call gmail_send_draft with this draft_id.",
    }


@google_mcp.tool(annotations=SEND)
def gmail_send_draft(draft_id: str, confirm: bool = False) -> dict:
    """Send a Gmail draft, in two calls.

    First call with confirm=false (the default): nothing is sent, it returns exactly what would go
    out. Show that to the user and ask. Only after the user clearly says yes, call again with
    confirm=true. The second call is refused if the draft changed since the preview, or if more
    than 15 minutes have passed."""
    details = _draft_details(draft_id)
    if not confirm:
        return send_guard.preview("gmail_send_draft", details)
    send_guard.confirm("gmail_send_draft", details)
    sent = gmail_client.send_draft(draft_id)
    return {"sent": True, "message_id": sent.get("id"), "thread_id": sent.get("threadId"), "to": details["to"], "subject": details["subject"]}
