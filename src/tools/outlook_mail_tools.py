"""Outlook.com sending, replies, invitations and bulk cleanup, on top of the upstream tools.

Sending works like Gmail: a draft first (outlook_create_draft or outlook_create_reply_draft), then
outlook_send_draft, which previews and only sends on a second call (utils/send_guard.py). Creating,
changing or deleting an event with attendees emails them, and so does answering an invitation, so
those event tools preview first too.

The bulk tools mirror the Gmail ones: outlook_top_senders finds who fills a folder, and
outlook_bulk_move moves every match in one call, paging and batching 20 moves per Graph request
server-side. Moving to "deleteditems" is the Outlook version of trashing.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from fastmcp.exceptions import ToolError
from outlook_personal_mcp.models import EventInput, shape_event
from outlook_personal_mcp.safety import graph_id
from outlook_personal_mcp.tools.mail import _compose_draft_body

from clients.outlook_client import outlook_graph
from constants.outlook_consts import GRAPH_BATCH, MESSAGE_PAGE_SIZE, WELL_KNOWN_FOLDERS
from constants.tool_annotations import DESTRUCTIVE, READ, SEND, WRITE
from server import google_mcp
from utils.send_guard import send_guard
from utils.text import html_to_text

SAMPLE_SIZE = 10
RETRY_DELAYS = (2, 4, 8, 16)
MAX_BULK = 5000  # most messages one bulk move may touch, whatever the caller asks for
EVENT_SELECT = "id,subject,start,end,location,isAllDay,organizer,attendees"
RESPONSE_ACTIONS = {"accept": "accept", "decline": "decline", "tentative": "tentativelyAccept"}


def _addresses(recipients: list[dict] | None) -> list[str]:
    return [r["emailAddress"]["address"] for r in recipients or []]


def _body(message: dict) -> str:
    body = message.get("body") or {}
    content = body.get("content") or ""
    return html_to_text(content) if str(body.get("contentType")).lower() == "html" else content.strip()


async def _folder_id(name_or_id: str, create: bool = False) -> str:
    """A folder id from a well-known name ("archive"), a display name ("Newsletters") or an id."""
    value = name_or_id.strip()
    if value.lower() in WELL_KNOWN_FOLDERS:
        return value.lower()
    escaped = value.replace("'", "''")
    for parent in ("/me/mailFolders", "/me/mailFolders/inbox/childFolders"):
        found = await outlook_graph.get(parent, params={"$filter": f"displayName eq '{escaped}'", "$select": "id"})
        if found.get("value"):
            return found["value"][0]["id"]
    if len(value) > 60 and " " not in value:
        return value  # looks like a Graph folder id already
    if create:
        return (await outlook_graph.post("/me/mailFolders", json={"displayName": value}))["id"]
    raise ToolError(f"No folder called {value!r}. Check outlook_list_folders, or pass create_destination=true.")


def _message_filter(from_addresses: list[str] | None, unread_only: bool, older_than_days: int | None) -> str | None:
    clauses = []
    if from_addresses:
        senders = " or ".join(f"from/emailAddress/address eq '{a.strip().lower().replace(chr(39), chr(39) * 2)}'" for a in from_addresses)
        clauses.append(f"({senders})")
    if unread_only:
        clauses.append("isRead eq false")
    if older_than_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        clauses.append(f"receivedDateTime lt {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    return " and ".join(clauses) or None


async def _list_messages(folder: str, limit: int, select: str, filter_: str | None = None, newest_first: bool = False) -> list[dict]:
    params = {"$top": min(MESSAGE_PAGE_SIZE, limit), "$select": select}
    if filter_:
        params["$filter"] = filter_
    if newest_first:
        params["$orderby"] = "receivedDateTime desc"
    page = await outlook_graph.get(f"/me/mailFolders/{graph_id(folder, name='folder')}/messages", params=params)
    out = page.get("value", [])
    while page.get("@odata.nextLink") and len(out) < limit:
        page = await outlook_graph.get(page["@odata.nextLink"])
        out += page.get("value", [])
    return out[:limit]


async def _move_all(ids: list[str], destination: str) -> tuple[int, int]:
    """Move messages 20 at a time with JSON batching, retrying throttled ones. (moved, failed)"""
    moved = failed = 0
    for start in range(0, len(ids), GRAPH_BATCH):
        pending = ids[start:start + GRAPH_BATCH]
        for delay in (*RETRY_DELAYS, None):
            requests = [
                {"id": str(i), "method": "POST", "url": f"/me/messages/{graph_id(mid)}/move",
                 "headers": {"Content-Type": "application/json"}, "body": {"destinationId": destination}}
                for i, mid in enumerate(pending)
            ]
            responses = (await outlook_graph.post("/$batch", json={"requests": requests})).get("responses", [])
            throttled = []
            for r in responses:
                if r.get("status", 500) < 300:
                    moved += 1
                elif r.get("status") in (429, 503) and delay is not None:
                    throttled.append(pending[int(r["id"])])
                else:
                    failed += 1
            if not throttled:
                break
            pending = throttled
            await asyncio.sleep(delay)
    return moved, failed


@google_mcp.tool(annotations=WRITE)
async def outlook_create_reply_draft(message_id: str, body: str, reply_all: bool = False) -> dict:
    """Write a reply to an Outlook email as a draft, in the same conversation. Nothing is sent.
    Show the user the draft, then use outlook_send_draft if they want it sent."""
    mid = graph_id(message_id, name="message_id")
    draft = await outlook_graph.post(f"/me/messages/{mid}/{'createReplyAll' if reply_all else 'createReply'}")
    did = graph_id(draft["id"], name="draft_id")
    await outlook_graph.patch(f"/me/messages/{did}", json={"body": _compose_draft_body(draft.get("body") or {}, body)})
    return {
        "draft_id": draft["id"],
        "to": _addresses(draft.get("toRecipients")),
        "subject": draft.get("subject"),
        "next": "Saved in the user's Outlook Drafts. To send it, call outlook_send_draft with this draft_id.",
    }


@google_mcp.tool(annotations=SEND)
async def outlook_send_draft(draft_id: str, confirm: bool = False) -> dict:
    """Send an Outlook draft, in two calls.

    First call with confirm=false (the default): nothing is sent, it returns exactly what would go
    out. Show that to the user and ask. Only after the user clearly says yes, call again with
    confirm=true. The second call is refused if the draft changed since the preview, or if more
    than 15 minutes have passed."""
    did = graph_id(draft_id, name="draft_id")
    m = await outlook_graph.get(f"/me/messages/{did}", params={"$select": "isDraft,subject,toRecipients,ccRecipients,bccRecipients,body,changeKey"})
    if not m.get("isDraft"):
        raise ToolError("That message isn't a draft; create one with outlook_create_draft or outlook_create_reply_draft")
    files = (await outlook_graph.get(f"/me/messages/{did}/attachments", params={"$select": "id,name,contentType,size,lastModifiedDateTime"})).get("value", [])
    details = {
        "draft_id": draft_id,
        "to": _addresses(m.get("toRecipients")),
        "cc": _addresses(m.get("ccRecipients")),
        "bcc": _addresses(m.get("bccRecipients")),
        "subject": m.get("subject"),
        "body": _body(m),
        "attachments": [{"name": f.get("name"), "type": f.get("contentType"), "bytes": f.get("size")} for f in files],
    }
    # The change key moves on every edit to the draft; with each attachment's id and modified time it
    # also catches a file swapped for another of the same name and size
    binding = [m.get("changeKey"), [(f.get("id"), f.get("lastModifiedDateTime")) for f in files]]
    if not confirm:
        return send_guard.preview("outlook_send_draft", details, binding)
    send_guard.confirm("outlook_send_draft", details, binding)
    # Graph sends a draft by id with no version check, so an edit landing in the moment between
    # this check and the send would still go out
    await outlook_graph.post(f"/me/messages/{did}/send")
    return {"sent": True, "to": details["to"], "subject": details["subject"]}


@google_mcp.tool(annotations=SEND)
async def outlook_create_event(
    subject: str,
    start: str,
    end: str,
    time_zone: str = "UTC",
    attendees: list[str] | None = None,
    location: str | None = None,
    body: str | None = None,
    confirm: bool = False,
) -> dict:
    """Add an event to the user's Outlook calendar. Times are ISO 8601 in time_zone, e.g.
    start="2026-11-03T14:00:00", time_zone="Europe/London".

    Without attendees it's created straight away. With attendees Outlook emails them invitations,
    so the first call (confirm=false) only previews: show it to the user, and call again with
    confirm=true once they agree."""
    payload = EventInput(subject=subject, start=start, end=end, time_zone=time_zone, attendees=attendees or [],
                         location=location, body=body).to_graph()
    if attendees:
        details = {"subject": subject, "start": f"{start} {time_zone}", "end": f"{end} {time_zone}",
                   "location": location, "invitations_to": attendees, "body": body}
        if not confirm:
            return send_guard.preview("outlook_create_event", details)
        send_guard.confirm("outlook_create_event", details)
    return shape_event(await outlook_graph.post("/me/events", json=payload))


async def _event(event_id: str) -> tuple[str, dict]:
    eid = graph_id(event_id, name="event_id")
    return eid, await outlook_graph.get(f"/me/events/{eid}", params={"$select": EVENT_SELECT})


@google_mcp.tool(annotations=SEND)
async def outlook_update_event(
    event_id: str,
    subject: str | None = None,
    start: str | None = None,
    end: str | None = None,
    time_zone: str = "UTC",
    location: str | None = None,
    confirm: bool = False,
) -> dict:
    """Change an Outlook event; only the fields given change. Times are ISO 8601 in time_zone.

    If the event has attendees, Outlook emails them the change, so the first call (confirm=false)
    only previews: show it to the user, and call again with confirm=true once they agree."""
    patch: dict = {}
    if subject is not None:
        patch["subject"] = subject
    if start is not None:
        patch["start"] = {"dateTime": start, "timeZone": time_zone}
    if end is not None:
        patch["end"] = {"dateTime": end, "timeZone": time_zone}
    if location is not None:
        patch["location"] = {"displayName": location}
    if not patch:
        raise ToolError("Nothing to change; give at least one field")
    eid, event = await _event(event_id)
    guests = _addresses(event.get("attendees"))
    if guests:
        details = {"event": shape_event(event), "changes": patch, "notifies": guests}
        if not confirm:
            return send_guard.preview("outlook_update_event", details)
        send_guard.confirm("outlook_update_event", details)
    return shape_event(await outlook_graph.patch(f"/me/events/{eid}", json=patch))


@google_mcp.tool(annotations=DESTRUCTIVE)
async def outlook_delete_event(event_id: str, confirm: bool = False) -> dict:
    """Delete an Outlook event. If it has attendees, Outlook emails them a cancellation, so the
    first call (confirm=false) only previews: show it to the user, and call again with
    confirm=true once they agree."""
    eid, event = await _event(event_id)
    guests = _addresses(event.get("attendees"))
    if guests:
        details = {"event": shape_event(event), "cancellation_to": guests}
        if not confirm:
            return send_guard.preview("outlook_delete_event", details)
        send_guard.confirm("outlook_delete_event", details)
    await outlook_graph.delete(f"/me/events/{eid}")
    return {"deleted": event_id, "subject": event.get("subject")}


@google_mcp.tool(annotations=SEND)
async def outlook_respond_event(
    event_id: str, response: str, comment: str = "", send_response: bool = True, confirm: bool = False
) -> dict:
    """Answer a meeting invitation: response is accept, decline or tentative.

    With send_response=true (the default) the organizer is emailed the answer and comment, so the
    first call (confirm=false) only previews: show it to the user, and call again with
    confirm=true once they agree. send_response=false only updates the user's own calendar."""
    action = RESPONSE_ACTIONS.get(response)
    if not action:
        raise ToolError("response must be accept, decline or tentative")
    eid, event = await _event(event_id)
    if send_response:
        organizer = ((event.get("organizer") or {}).get("emailAddress") or {}).get("address")
        details = {"event": shape_event(event), "response": response, "comment": comment, "emails": organizer}
        if not confirm:
            return send_guard.preview("outlook_respond_event", details)
        send_guard.confirm("outlook_respond_event", details)
    await outlook_graph.post(f"/me/events/{eid}/{action}", json={"comment": comment, "sendResponse": send_response})
    return {"event_id": event_id, "response": response, "organizer_notified": send_response}


@google_mcp.tool(annotations=READ)
async def outlook_top_senders(folder: str = "inbox", unread_only: bool = False, sample_size: int = 500, top: int = 25) -> dict:
    """Find who sends the mail in an Outlook folder, to decide what to bulk-move.

    Reads the newest sample_size (max 2000) messages of the folder ("inbox", "junkemail", a folder
    name...) and groups them by sender. Each sender comes with the from_addresses to pass to
    outlook_bulk_move."""
    folder_id = await _folder_id(folder)
    counts = await outlook_graph.get(f"/me/mailFolders/{graph_id(folder_id, name='folder')}", params={"$select": "totalItemCount,unreadItemCount"})
    msgs = await _list_messages(folder_id, max(1, min(sample_size, 2000)), "from", "isRead eq false" if unread_only else None, newest_first=True)
    senders: dict[str, dict] = {}
    for m in msgs:
        sender = (m.get("from") or {}).get("emailAddress") or {}
        addr = (sender.get("address") or "").lower()
        s = senders.setdefault(addr, {"email": addr, "name": sender.get("name"), "count": 0})
        s["count"] += 1
    ranked = sorted(senders.values(), key=lambda s: s["count"], reverse=True)[:top]
    for s in ranked:
        s["from_addresses"] = [s["email"]]
    return {
        "folder": folder,
        "total_in_folder": counts.get("totalItemCount"),
        "unread_in_folder": counts.get("unreadItemCount"),
        "sampled": len(msgs),
        "senders": ranked,
    }


@google_mcp.tool(annotations=DESTRUCTIVE)
async def outlook_bulk_move(
    destination: str,
    from_addresses: list[str] | None = None,
    folder: str = "inbox",
    unread_only: bool = False,
    older_than_days: int | None = None,
    dry_run: bool = True,
    create_destination: bool = False,
    max_messages: int = MAX_BULK,
    confirm_token: str | None = None,
) -> dict:
    """Move EVERY Outlook message matching the filters to another folder in one call (up to 5000).

    destination: a folder name ("Newsletters"), a well-known folder ("archive", "deleteditems" to
    trash, "junkemail") or an id; create_destination=true makes the folder if it doesn't exist.
    Filters combine: from_addresses (any of them), unread_only, older_than_days, within `folder`.
    At least one filter is required. Always call with dry_run=true first (the default): it returns
    the match count, a sample and a confirm_token. You MUST show the user the count and sample and
    get their confirmation, then call again with the same arguments, dry_run=false and that
    confirm_token. Only the messages the dry run found are moved, not mail that arrived since.
    Moves can be undone by moving back, and Deleted Items keeps mail until the user empties it."""
    filter_ = _message_filter(from_addresses, unread_only, older_than_days)
    if not filter_:
        raise ToolError("Give at least one filter (from_addresses, unread_only or older_than_days); moving a whole folder is too broad")
    max_messages = max(1, min(max_messages, MAX_BULK))
    # The arguments rather than filter_, whose older_than_days cutoff moves with the clock
    params = {"destination": destination, "from_addresses": sorted(a.strip().lower() for a in from_addresses or []),
              "folder": folder, "unread_only": unread_only, "older_than_days": older_than_days,
              "create_destination": create_destination, "max_messages": max_messages}

    if not dry_run:
        ids, more_remaining = send_guard.take("outlook_bulk_move", params, confirm_token)
        destination_id = await _folder_id(destination, create=create_destination)
        moved, failed = await _move_all(ids, destination_id)
        return {"dry_run": False, "folder": folder, "destination": destination, "moved": moved, "failed": failed, "more_remaining": more_remaining}

    source = await _folder_id(folder)
    msgs = await _list_messages(source, max_messages + 1, "id,from,subject,receivedDateTime", filter_)
    more_remaining = len(msgs) > max_messages
    msgs = msgs[:max_messages]
    return {
        "dry_run": True,
        "folder": folder,
        "destination": destination,
        "would_move": len(msgs),
        "more_than_max_messages": more_remaining,
        "sample": [
            {"from": (m.get("from") or {}).get("emailAddress", {}).get("address"), "subject": m.get("subject"), "received": m.get("receivedDateTime")}
            for m in msgs[:SAMPLE_SIZE]
        ],
        "confirm_token": send_guard.hold("outlook_bulk_move", params, ([m["id"] for m in msgs], more_remaining)),
    }
