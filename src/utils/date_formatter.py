
from datetime import date, datetime, timezone
from fastmcp.exceptions import ToolError 


def _due(value: str | None) -> str | None:
    """Accept YYYY-MM-DD or a full ISO datetime; Google Tasks only keeps the date part."""
    if not value:
        return None
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        raise ToolError(f"Invalid due date {value!r}; use YYYY-MM-DD")
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")