"""Remote MCP server exposing Google Tasks (official API) and Google Keep (unofficial gkeepapi).

Served over Streamable HTTP at /<MCP_SECRET>/mcp so it can be added to Claude as a custom connector.
"""

import os
import threading
from datetime import date, datetime, timezone
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

TASKS_SCOPES = ["https://www.googleapis.com/auth/tasks"]

mcp = FastMCP(
    "google-keep-tasks",
    instructions=(
        "Tools for the user's Google Tasks and Google Keep. "
        "Call tasks_list_tasklists first to get tasklist ids; '@default' is the user's default list."
    ),
)


# ---------------------------------------------------------------- Google Tasks

_tasks_service = None
_tasks_lock = threading.Lock()


def _tasks():
    global _tasks_service
    if _tasks_service is None:
        missing = [k for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN") if not os.environ.get(k)]
        if missing:
            raise ToolError(f"Google Tasks is not configured; missing env vars: {', '.join(missing)}")
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=TASKS_SCOPES,
        )
        _tasks_service = build("tasks", "v1", credentials=creds, cache_discovery=False)
    return _tasks_service


def _due(value: str | None) -> str | None:
    """Accept YYYY-MM-DD or a full ISO datetime; Google Tasks only keeps the date part."""
    if not value:
        return None
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        raise ToolError(f"Invalid due date {value!r}; use YYYY-MM-DD")
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _task_view(t: dict) -> dict:
    keys = ("id", "title", "notes", "status", "due", "completed", "parent", "updated", "webViewLink")
    return {k: t[k] for k in keys if k in t}


@mcp.tool
def tasks_list_tasklists() -> list[dict]:
    """List all of the user's Google Tasks lists (id and title)."""
    with _tasks_lock:
        resp = _tasks().tasklists().list(maxResults=100).execute()
    return [{"id": l["id"], "title": l["title"]} for l in resp.get("items", [])]


@mcp.tool
def tasks_create_tasklist(title: str) -> dict:
    """Create a new Google Tasks list."""
    with _tasks_lock:
        l = _tasks().tasklists().insert(body={"title": title}).execute()
    return {"id": l["id"], "title": l["title"]}


@mcp.tool
def tasks_list_tasks(tasklist_id: str = "@default", show_completed: bool = False, due_max: str | None = None) -> list[dict]:
    """List tasks in a task list. due_max (YYYY-MM-DD) limits to tasks due on or before that date."""
    params = {"tasklist": tasklist_id, "showCompleted": show_completed, "showHidden": show_completed, "maxResults": 100}
    if due_max:
        params["dueMax"] = _due(due_max)
    items, token = [], None
    with _tasks_lock:
        while True:
            resp = _tasks().tasks().list(pageToken=token, **params).execute()
            items += resp.get("items", [])
            token = resp.get("nextPageToken")
            if not token:
                break
    return [_task_view(t) for t in items]


@mcp.tool
def tasks_create_task(
    title: str,
    tasklist_id: str = "@default",
    notes: str | None = None,
    due: str | None = None,
    parent_task_id: str | None = None,
) -> dict:
    """Create a task. due is YYYY-MM-DD (Google Tasks does not store a time of day)."""
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = _due(due)
    with _tasks_lock:
        t = _tasks().tasks().insert(tasklist=tasklist_id, body=body, parent=parent_task_id).execute()
    return _task_view(t)


@mcp.tool
def tasks_update_task(
    task_id: str,
    tasklist_id: str = "@default",
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: Literal["needsAction", "completed"] | None = None,
) -> dict:
    """Update fields of a task. Set status='completed' to tick it off, 'needsAction' to reopen it."""
    body = {}
    if title is not None:
        body["title"] = title
    if notes is not None:
        body["notes"] = notes
    if due is not None:
        body["due"] = _due(due)
    if status is not None:
        body["status"] = status
        if status == "needsAction":
            body["completed"] = None
    if not body:
        raise ToolError("Nothing to update")
    with _tasks_lock:
        t = _tasks().tasks().patch(tasklist=tasklist_id, task=task_id, body=body).execute()
    return _task_view(t)


@mcp.tool
def tasks_delete_task(task_id: str, tasklist_id: str = "@default") -> str:
    """Permanently delete a task."""
    with _tasks_lock:
        _tasks().tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return "deleted"


# ---------------------------------------------------------------- Google Keep

_keep = None
_keep_lock = threading.Lock()


def _keep_client():
    """Return a synced gkeepapi client. Caller must hold _keep_lock."""
    global _keep
    if _keep is None:
        email, token = os.environ.get("KEEP_EMAIL"), os.environ.get("KEEP_MASTER_TOKEN")
        if not (email and token):
            raise ToolError("Google Keep is not configured; set KEEP_EMAIL and KEEP_MASTER_TOKEN")
        import gkeepapi

        keep = gkeepapi.Keep()
        keep.authenticate(email, token)
        _keep = keep
    else:
        _keep.sync()
    return _keep


def _note_view(n, full: bool = True) -> dict:
    import gkeepapi

    out = {
        "id": n.id,
        "title": n.title,
        "type": "list" if isinstance(n, gkeepapi.node.List) else "note",
        "pinned": n.pinned,
        "archived": n.archived,
        "color": n.color.value,
        "labels": [l.name for l in n.labels.all()],
        "updated": n.timestamps.updated.isoformat(),
    }
    if isinstance(n, gkeepapi.node.List):
        items = [{"id": i.id, "text": i.text, "checked": i.checked} for i in n.items]
        out["items"] = items if full else items[:10]
    else:
        out["text"] = n.text if full else n.text[:300]
    return out


def _get_note(keep, note_id: str):
    n = keep.get(note_id)
    if n is None or n.trashed:
        raise ToolError(f"No note with id {note_id}")
    return n


@mcp.tool
def keep_search_notes(
    query: str | None = None,
    label: str | None = None,
    pinned: bool | None = None,
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Search Google Keep notes by text in title/body and/or label. Omit query to list recent notes.
    Results are previews (text truncated); use keep_get_note for full content."""
    with _keep_lock:
        keep = _keep_client()
        labels = None
        if label:
            l = keep.findLabel(label)
            if l is None:
                raise ToolError(f"No label named {label!r}")
            labels = [l]
        notes = keep.find(
            query=query or None,
            labels=labels,
            pinned=pinned,
            archived=None if include_archived else False,
        )
        notes = sorted(notes, key=lambda n: n.timestamps.updated, reverse=True)[:limit]
        return [_note_view(n, full=False) for n in notes]


@mcp.tool
def keep_get_note(note_id: str) -> dict:
    """Get the full content of a Google Keep note or checklist."""
    with _keep_lock:
        return _note_view(_get_note(_keep_client(), note_id))


@mcp.tool
def keep_create_note(title: str, text: str = "", label: str | None = None, pinned: bool = False) -> dict:
    """Create a Google Keep text note. The label is created if it doesn't exist."""
    with _keep_lock:
        keep = _keep_client()
        n = keep.createNote(title, text)
        n.pinned = pinned
        if label:
            n.labels.add(keep.findLabel(label, create=True))
        keep.sync()
        return _note_view(n)


@mcp.tool
def keep_create_list(title: str, items: list[str], label: str | None = None, pinned: bool = False) -> dict:
    """Create a Google Keep checklist with the given unchecked items."""
    with _keep_lock:
        keep = _keep_client()
        n = keep.createList(title, [(i, False) for i in items])
        n.pinned = pinned
        if label:
            n.labels.add(keep.findLabel(label, create=True))
        keep.sync()
        return _note_view(n)


@mcp.tool
def keep_update_note(
    note_id: str,
    title: str | None = None,
    text: str | None = None,
    append_text: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> dict:
    """Edit a Keep note: replace title/text, append text to the end, pin/unpin or archive/unarchive."""
    with _keep_lock:
        keep = _keep_client()
        n = _get_note(keep, note_id)
        if title is not None:
            n.title = title
        if text is not None:
            n.text = text
        if append_text:
            n.text = (n.text + "\n" if n.text else "") + append_text
        if pinned is not None:
            n.pinned = pinned
        if archived is not None:
            n.archived = archived
        keep.sync()
        return _note_view(n)


@mcp.tool
def keep_update_list(
    note_id: str,
    add_items: list[str] | None = None,
    check_item_ids: list[str] | None = None,
    uncheck_item_ids: list[str] | None = None,
    delete_item_ids: list[str] | None = None,
) -> dict:
    """Modify a Keep checklist: add items, check/uncheck or delete items by their item id."""
    import gkeepapi

    with _keep_lock:
        keep = _keep_client()
        n = _get_note(keep, note_id)
        if not isinstance(n, gkeepapi.node.List):
            raise ToolError("That note is not a checklist")
        by_id = {i.id: i for i in n.items}
        for iid in check_item_ids or []:
            by_id[iid].checked = True
        for iid in uncheck_item_ids or []:
            by_id[iid].checked = False
        for iid in delete_item_ids or []:
            by_id[iid].delete()
        for text in add_items or []:
            n.add(text, False)
        keep.sync()
        return _note_view(n)


@mcp.tool
def keep_trash_note(note_id: str) -> str:
    """Move a Keep note to the trash (recoverable in Keep for 7 days)."""
    with _keep_lock:
        keep = _keep_client()
        _get_note(keep, note_id).trash()
        keep.sync()
    return "trashed"


# ---------------------------------------------------------------- entrypoint

if __name__ == "__main__":
    secret = os.environ.get("MCP_SECRET")
    if not secret or len(secret) < 24:
        raise SystemExit("Set MCP_SECRET to a random string of 24+ chars (it becomes part of the URL)")
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path=f"/{secret}/mcp",
        stateless_http=True,
    )
