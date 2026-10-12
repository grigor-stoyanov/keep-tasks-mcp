from typing import Callable


def collect_pages(fetch: Callable[..., dict], **params) -> list[dict]:
    """Call fetch(pageToken=..., **params) until Google stops returning nextPageToken.

    Returns all "items" from every page combined.
    """
    items: list[dict] = []
    token = None
    while True:
        resp = fetch(pageToken=token, **params)
        items += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            return items
