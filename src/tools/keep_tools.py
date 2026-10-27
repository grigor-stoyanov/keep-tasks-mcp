import gkeepapi
from fastmcp.exceptions import ToolError

from clients.keep_client import keep_client
from constants.tool_annotations import DESTRUCTIVE, READ, WRITE
from server import google_mcp
from utils.keep_parser import _note_view


def _get_note(note_id: str):
    n = keep_client.get(note_id)
    if n is None or n.trashed:
        raise ToolError(f"No note with id {note_id}")
    return n


@google_mcp.tool(annotations=READ)
def keep_search_notes(
    query: str | None = None,
    label: str | None = None,
    pinned: bool | None = None,
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Search Google Keep notes by text in title/body and/or label. Omit query to list recent notes.
    Results are previews (text truncated); use keep_get_note for full content."""
    labels = None
    if label:
        found = keep_client.find_label(label)
        if found is None:
            raise ToolError(f"No label named {label!r}")
        labels = [found]
    notes = keep_client.find(
        query=query or None,
        labels=labels,
        pinned=pinned,
        archived=None if include_archived else False,
    )
    notes = sorted(notes, key=lambda n: n.timestamps.updated, reverse=True)[:limit]
    return [_note_view(n, full=False) for n in notes]


@google_mcp.tool(annotations=READ)
def keep_get_note(note_id: str) -> dict:
    """Get the full content of a Google Keep note or checklist."""
    return _note_view(_get_note(note_id))


@google_mcp.tool(annotations=WRITE)
def keep_create_note(title: str, text: str = "", label: str | None = None, pinned: bool = False) -> dict:
    """Create a Google Keep text note. The label is created if it doesn't exist."""
    n = keep_client.create_note(title, text)
    n.pinned = pinned
    if label:
        n.labels.add(keep_client.find_label(label, create=True))
    keep_client.sync()
    return _note_view(n)


@google_mcp.tool(annotations=WRITE)
def keep_create_list(title: str, items: list[str], label: str | None = None, pinned: bool = False) -> dict:
    """Create a Google Keep checklist with the given unchecked items."""
    n = keep_client.create_list(title, [(i, False) for i in items])
    n.pinned = pinned
    if label:
        n.labels.add(keep_client.find_label(label, create=True))
    keep_client.sync()
    return _note_view(n)


@google_mcp.tool(annotations=DESTRUCTIVE)
def keep_update_note(
    note_id: str,
    title: str | None = None,
    text: str | None = None,
    append_text: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> dict:
    """Edit a Keep note: replace title/text, append text to the end, pin/unpin or archive/unarchive."""
    n = _get_note(note_id)
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
    keep_client.sync()
    return _note_view(n)


@google_mcp.tool(annotations=DESTRUCTIVE)
def keep_update_list(
    note_id: str,
    add_items: list[str] | None = None,
    check_item_ids: list[str] | None = None,
    uncheck_item_ids: list[str] | None = None,
    delete_item_ids: list[str] | None = None,
) -> dict:
    """Modify a Keep checklist: add items, check/uncheck or delete items by their item id."""
    n = _get_note(note_id)
    if not isinstance(n, gkeepapi.node.List):
        raise ToolError("That note is not a checklist")
    by_id = {i.id: i for i in n.items}
    requested = (check_item_ids or []) + (uncheck_item_ids or []) + (delete_item_ids or [])
    unknown = [iid for iid in requested if iid not in by_id]
    if unknown:
        raise ToolError(f"Unknown item ids: {', '.join(unknown)}")
    for iid in check_item_ids or []:
        by_id[iid].checked = True
    for iid in uncheck_item_ids or []:
        by_id[iid].checked = False
    for iid in delete_item_ids or []:
        by_id[iid].delete()
    for text in add_items or []:
        n.add(text, False)
    keep_client.sync()
    return _note_view(n)


@google_mcp.tool(annotations=DESTRUCTIVE)
def keep_trash_note(note_id: str) -> str:
    """Move a Keep note to the trash (recoverable in Keep for 7 days)."""
    _get_note(note_id).trash()
    keep_client.sync()
    return "trashed"
