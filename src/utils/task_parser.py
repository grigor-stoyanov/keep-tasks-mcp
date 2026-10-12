def _task_view(t: dict) -> dict:
    keys = ("id", "title", "notes", "status", "due", "completed", "parent", "updated", "webViewLink")
    return {k: t[k] for k in keys if k in t}