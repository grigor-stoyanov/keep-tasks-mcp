import gkeepapi


def _note_view(n, full: bool = True) -> dict:
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
