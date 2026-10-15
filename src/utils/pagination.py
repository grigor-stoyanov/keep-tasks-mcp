from typing import Callable


def collect_pages(fetch: Callable[..., dict], key: str = "items", limit: int | None = None, **params) -> list[dict]:
    """Call fetch(pageToken=..., **params) until Google stops returning nextPageToken.

    Returns the `key` list from every page combined (Tasks uses "items", Gmail "messages"),
    stopping early once `limit` entries have been collected.
    """
    items: list[dict] = []
    token = None
    while True:
        resp = fetch(pageToken=token, **params)
        items += resp.get(key, [])
        token = resp.get("nextPageToken")
        if not token or (limit is not None and len(items) >= limit):
            return items[:limit] if limit is not None else items
