"""Microsoft To Do, the task lists that come with an Outlook.com account, through Microsoft Graph.

Same Microsoft sign-in as the Outlook tools (Tasks.ReadWrite). Omitting list_id means the user's
default "Tasks" list.
"""
from fastmcp.exceptions import ToolError
from outlook_personal_mcp.safety import graph_id

from clients.outlook_client import outlook_graph
from constants.tool_annotations import DESTRUCTIVE, READ, WRITE
from server import google_mcp

IMPORTANCE = ("low", "normal", "high")
MAX_TASKS = 500


async def _list_id(list_id: str | None) -> str:
    if list_id:
        return graph_id(list_id, name="list_id")
    lists = (await outlook_graph.get("/me/todo/lists")).get("value", [])
    default = next((l for l in lists if l.get("wellknownListName") == "defaultList"), lists[0] if lists else None)
    if default is None:
        raise ToolError("This account has no To Do lists yet")
    return graph_id(default["id"], name="list_id")


def _task_view(t: dict) -> dict:
    due = (t.get("dueDateTime") or {}).get("dateTime")
    return {
        "id": t.get("id"),
        "title": t.get("title"),
        "completed": t.get("status") == "completed",
        "importance": t.get("importance"),
        "due": due[:10] if due else None,
        "note": ((t.get("body") or {}).get("content") or "").strip() or None,
    }


def _fields(title, due_date, note, importance) -> dict:
    body = {}
    if title is not None:
        body["title"] = title
    if due_date is not None:
        # To Do keeps due dates as a day; midnight UTC shows as that day in every time zone's list
        body["dueDateTime"] = {"dateTime": f"{due_date}T00:00:00", "timeZone": "UTC"} if due_date else None
    if note is not None:
        body["body"] = {"content": note, "contentType": "text"}
    if importance is not None:
        if importance not in IMPORTANCE:
            raise ToolError(f"importance must be one of {', '.join(IMPORTANCE)}")
        body["importance"] = importance
    return body


@google_mcp.tool(annotations=READ)
async def outlook_todo_list_lists() -> dict:
    """The user's Microsoft To Do lists with their ids. The default one is called Tasks."""
    lists = (await outlook_graph.get("/me/todo/lists")).get("value", [])
    return {"lists": [{"id": l["id"], "name": l.get("displayName"), "default": l.get("wellknownListName") == "defaultList"} for l in lists]}


@google_mcp.tool(annotations=READ)
async def outlook_todo_list_tasks(list_id: str | None = None, include_completed: bool = False, max_results: int = 100) -> dict:
    """Tasks in a Microsoft To Do list (default: the Tasks list), open ones only unless include_completed.
    At most 500."""
    max_results = max(1, min(max_results, MAX_TASKS))
    params = {"$top": min(max_results, 100)}
    if not include_completed:
        params["$filter"] = "status ne 'completed'"
    page = await outlook_graph.get(f"/me/todo/lists/{await _list_id(list_id)}/tasks", params=params)
    tasks = page.get("value", [])
    while page.get("@odata.nextLink") and len(tasks) < max_results:
        page = await outlook_graph.get(page["@odata.nextLink"])
        tasks += page.get("value", [])
    return {"tasks": [_task_view(t) for t in tasks[:max_results]]}


@google_mcp.tool(annotations=WRITE)
async def outlook_todo_create_task(
    title: str,
    list_id: str | None = None,
    due_date: str | None = None,
    note: str | None = None,
    importance: str = "normal",
) -> dict:
    """Add a task to Microsoft To Do (default: the Tasks list). due_date is YYYY-MM-DD."""
    body = _fields(title, due_date, note, importance)
    return _task_view(await outlook_graph.post(f"/me/todo/lists/{await _list_id(list_id)}/tasks", json=body))


@google_mcp.tool(annotations=DESTRUCTIVE)
async def outlook_todo_update_task(
    task_id: str,
    list_id: str | None = None,
    title: str | None = None,
    due_date: str | None = None,
    note: str | None = None,
    importance: str | None = None,
    completed: bool | None = None,
) -> dict:
    """Change a To Do task; only the fields given change. completed=true ticks it off,
    due_date="" removes the due date, note replaces the existing note."""
    body = _fields(title, due_date, note, importance)
    if completed is not None:
        body["status"] = "completed" if completed else "notStarted"
    if not body:
        raise ToolError("Nothing to change; give at least one field")
    path = f"/me/todo/lists/{await _list_id(list_id)}/tasks/{graph_id(task_id, name='task_id')}"
    return _task_view(await outlook_graph.patch(path, json=body))


@google_mcp.tool(annotations=DESTRUCTIVE)
async def outlook_todo_delete_task(task_id: str, list_id: str | None = None) -> dict:
    """Delete a To Do task for good (To Do has no bin). To just tick it off, use
    outlook_todo_update_task with completed=true."""
    await outlook_graph.delete(f"/me/todo/lists/{await _list_id(list_id)}/tasks/{graph_id(task_id, name='task_id')}")
    return {"deleted": task_id}
