from typing import Literal

from fastmcp.exceptions import ToolError

from clients.task_client import task_client
from server import google_mcp
from utils.date_formatter import _due
from utils.pagination import collect_pages
from utils.task_parser import _task_view


@google_mcp.tool
def tasks_list_tasklists() -> list[dict]:
    """List all of the user's Google Tasks lists (id and title)."""
    lists = collect_pages(task_client.list_tasklists, maxResults=100)
    return [{"id": l["id"], "title": l["title"]} for l in lists]


@google_mcp.tool
def tasks_create_tasklist(title: str) -> dict:
    """Create a new Google Tasks list."""
    resp = task_client.create_tasklist(body={"title": title})
    return {"id": resp["id"], "title": resp["title"]}


@google_mcp.tool
def tasks_list_tasks(tasklist_id: str = "@default", show_completed: bool = False, due_max: str | None = None) -> list[dict]:
    """List tasks in a task list. due_max (YYYY-MM-DD) limits to tasks due on or before that date."""
    params = {"showCompleted": show_completed, "showHidden": show_completed, "maxResults": 100}
    if due_max:
        params["dueMax"] = _due(due_max)
    items = collect_pages(task_client.list_tasks, tasklist=tasklist_id, **params)
    return [_task_view(t) for t in items]


@google_mcp.tool
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
    resp = task_client.create_task(tasklist=tasklist_id, body=body, parent=parent_task_id)
    return _task_view(resp)


@google_mcp.tool
def tasks_update_task(
    task_id: str,
    title: str | None,
    notes: str | None,
    due: str | None,
    status: Literal["needsAction", "completed"] | None,
    tasklist_id: str = "@default",
) -> dict:
    """Update a task. ALL of title, notes, due and status are required: pass the current value for fields you do not want to change.
    Set status='completed' to tick it off, 'needsAction' to reopen it."""
    fields = {"title": title, "notes": notes, "due": due, "status": status}
    for name, value in fields.items():
        if value is None:
            raise ToolError(f"{name} cannot be None; send the full task (current value if unchanged)")
    body = {"title": title, "notes": notes, "due": _due(due), "status": status}
    if status == "needsAction":
        body["completed"] = None
    resp = task_client.patch_task(tasklist=tasklist_id, task=task_id, body=body)
    return _task_view(resp)


# TODO: add rollback in memory
@google_mcp.tool
def tasks_delete_task(task_id: str, tasklist_id: str = "@default") -> str:
    """Permanently delete a task."""
    task_client.delete_task(tasklist=tasklist_id, task=task_id)
    return "deleted"


@google_mcp.tool
def tasks_get_task_by_title(title: str, tasklist_id: str = "@default") -> dict | None:
    """Get a task by exact title (completed tasks included). Returns None if not found."""
    items = collect_pages(
        task_client.list_tasks, tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100
    )
    for t in items:
        if t.get("title") == title:
            return _task_view(t)
    return None
