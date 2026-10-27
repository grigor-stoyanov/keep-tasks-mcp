"""Bulk Gmail cleanup driven by Gmail search queries.

The model never handles message ids: each tool takes one search query and does all the paging,
header fetching and chunked batchModify calls server-side, so clearing thousands of messages is
a single tool call. Everything goes to Trash (recoverable for 30 days), never permanent deletion.
"""
import time

from fastmcp.exceptions import ToolError

from clients.gmail_client import gmail_client
from constants.gmail_consts import LIST_PAGE_SIZE, METADATA_BATCH, MODIFY_CHUNK
from constants.tool_annotations import DESTRUCTIVE, READ, WRITE
from server import google_mcp
from utils.gmail_parser import _header, _message_view, _sender
from utils.pagination import collect_pages

COUNT_CAP = 50000  # stop listing ids past this; a query that broad needs narrowing anyway
SAMPLE_SIZE = 10


def _list_ids(query: str, limit: int, include_trash: bool = False) -> list[str]:
    msgs = collect_pages(
        gmail_client.list_messages, key="messages", limit=limit,
        q=query, maxResults=LIST_PAGE_SIZE, includeSpamTrash=include_trash, fields="messages/id,nextPageToken",
    )
    return [m["id"] for m in msgs]


def _fetch_headers(ids: list[str], headers: list[str]) -> list[dict]:
    """Headers of each message, newest first. Retries rate-limited sub-requests with backoff."""
    out = []
    for start in range(0, len(ids), METADATA_BATCH):
        pending = ids[start:start + METADATA_BATCH]
        for attempt in range(5):
            got, pending = gmail_client.get_metadata(pending, headers)
            out += got
            if not pending:
                break
            time.sleep(2 ** attempt)
    return sorted(out, key=lambda m: int(m.get("internalDate", 0)), reverse=True)


def _modify(ids: list[str], add: list[str] | None = None, remove: list[str] | None = None) -> None:
    for start in range(0, len(ids), MODIFY_CHUNK):
        body = {"ids": ids[start:start + MODIFY_CHUNK], "addLabelIds": add or [], "removeLabelIds": remove or []}
        gmail_client.batch_modify(body)


def _require_query(query: str) -> str:
    if not query.strip():
        raise ToolError("query cannot be empty; an empty Gmail query matches every message")
    return query.strip()


@google_mcp.tool(annotations=READ)
def gmail_top_senders(query: str = "category:promotions is:unread", sample_size: int = 500, top: int = 25) -> dict:
    """Find who sends the mail matching a Gmail search query, to decide what to bulk-trash.

    Counts every match, then reads the From and List-Unsubscribe headers of the newest sample_size
    (max 2000) and groups them by sender. has_unsubscribe=true is a strong sign of marketing mail.
    Each sender comes with a ready-made `query` to pass to gmail_bulk_trash."""
    query = _require_query(query)
    sample_size = max(1, min(sample_size, 2000))
    ids = _list_ids(query, limit=COUNT_CAP)
    msgs = _fetch_headers(ids[:sample_size], ["From", "List-Unsubscribe"])

    senders: dict[str, dict] = {}
    for m in msgs:
        name, addr = _sender(m)
        s = senders.setdefault(addr, {"email": addr, "name": name, "count": 0, "has_unsubscribe": False})
        s["count"] += 1
        s["has_unsubscribe"] |= _header(m, "List-Unsubscribe") is not None
    ranked = sorted(senders.values(), key=lambda s: s["count"], reverse=True)[:top]
    for s in ranked:
        s["query"] = f"from:{s['email']}"
    return {
        "query": query,
        "matching": len(ids),
        "matching_capped": len(ids) >= COUNT_CAP,
        "sampled": len(msgs),
        "senders": ranked,
    }


@google_mcp.tool(annotations=DESTRUCTIVE)
def gmail_bulk_trash(query: str, dry_run: bool = True, keep_starred: bool = True, max_messages: int = 20000) -> dict:
    """Move EVERY message matching a Gmail search query to Trash in one call (any number of messages).

    Uses Gmail search syntax, e.g. "from:news@shop.com", "category:promotions is:unread older_than:1y",
    "from:(a@x.com OR b@y.com)". Starred mail is skipped unless keep_starred=false.
    Always call with dry_run=true first (the default): it returns the match count and a sample,
    which you MUST show the user and get their confirmation before calling again with dry_run=false.
    Trashed mail can be undone for 30 days with gmail_restore_from_trash."""
    query = _require_query(query)
    effective = f"({query}) -is:starred" if keep_starred else query
    ids = _list_ids(effective, limit=max_messages + 1)
    more_remaining = len(ids) > max_messages
    ids = ids[:max_messages]

    if dry_run:
        sample = _fetch_headers(ids[:SAMPLE_SIZE], ["From", "Subject", "Date"])
        return {
            "dry_run": True,
            "query": effective,
            "would_trash": len(ids),
            "more_than_max_messages": more_remaining,
            "sample": [_message_view(m) for m in sample],
        }

    _modify(ids, add=["TRASH"])
    return {
        "dry_run": False,
        "query": effective,
        "trashed": len(ids),
        "more_remaining": more_remaining,
        "undo": f"gmail_restore_from_trash(query={query!r})",
    }


@google_mcp.tool(annotations=WRITE)
def gmail_restore_from_trash(query: str, max_messages: int = 20000) -> dict:
    """Undo gmail_bulk_trash: move messages in Trash that match a Gmail search query back out of Trash.
    Pass the same query that was used to trash them."""
    query = _require_query(query)
    ids = _list_ids(f"in:trash ({query})", limit=max_messages, include_trash=True)
    _modify(ids, remove=["TRASH"])
    return {"query": query, "restored": len(ids)}
