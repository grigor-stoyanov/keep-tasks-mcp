"""Google Calendar: see, add, change and remove events.

Anything that emails guests (a new event with attendees, or changing or deleting an event that
has guests) previews first and only goes ahead on a second call with confirm=true
(utils/send_guard.py). Events without guests are changed straight away.
"""
from datetime import datetime, timedelta, timezone

from fastmcp.exceptions import ToolError

from clients.calendar_client import calendar_client
from constants.calendar_consts import MAX_EVENTS
from constants.tool_annotations import DESTRUCTIVE, READ, SEND
from server import google_mcp
from utils.send_guard import send_guard

DEFAULT_DAYS = 7


def _rfc3339(value: str) -> str:
    """Google wants an offset on timeMin/timeMax; a bare date or time is read as UTC."""
    if len(value) == 10:
        return f"{value}T00:00:00Z"
    return value if value.endswith("Z") or "+" in value[10:] or "-" in value[10:] else f"{value}Z"


def _when(value: str, time_zone: str | None, calendar_id: str) -> dict:
    """A start/end for the API: a date for all-day events, else a date-time in time_zone."""
    if len(value) == 10:
        return {"date": value}
    return {"dateTime": value, "timeZone": time_zone or calendar_client.get_calendar(calendar_id)["timeZone"]}


def _event_view(e: dict) -> dict:
    start, end = e.get("start", {}), e.get("end", {})
    return {
        "id": e.get("id"),
        "summary": e.get("summary"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "location": e.get("location"),
        "attendees": [a.get("email") for a in e.get("attendees", [])],
        "organizer": e.get("organizer", {}).get("email"),
        "link": e.get("htmlLink"),
    }


@google_mcp.tool(annotations=READ)
def calendar_list_calendars() -> dict:
    """The user's Google calendars with their ids; "primary" always means the main one."""
    items = calendar_client.list_calendars(fields="items(id,summary,primary,accessRole,timeZone)").get("items", [])
    return {"calendars": [{"id": c["id"], "name": c.get("summary"), "primary": c.get("primary", False),
                           "access": c.get("accessRole"), "time_zone": c.get("timeZone")} for c in items]}


@google_mcp.tool(annotations=READ)
def calendar_list_events(
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    calendar_id: str = "primary",
    max_results: int = 50,
) -> dict:
    """Events between time_min and time_max (default: the next 7 days), soonest first.

    Times are RFC 3339 with an offset, e.g. "2026-11-03T00:00:00+01:00", or a date "2026-11-03"
    (read as UTC midnight). query searches titles, descriptions, locations and attendees."""
    now = datetime.now(timezone.utc)
    params = {
        "timeMin": _rfc3339(time_min) if time_min else now.isoformat(),
        "timeMax": _rfc3339(time_max) if time_max else (now + timedelta(days=DEFAULT_DAYS)).isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max(1, min(max_results, MAX_EVENTS)),
    }
    if query:
        params["q"] = query
    events = calendar_client.list_events(calendar_id, **params)
    return {"time_zone": events.get("timeZone"), "events": [_event_view(e) for e in events.get("items", [])]}


@google_mcp.tool(annotations=SEND)
def calendar_create_event(
    summary: str,
    start: str,
    end: str,
    time_zone: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
    confirm: bool = False,
) -> dict:
    """Add an event to Google Calendar.

    start/end: "2026-11-03T14:00:00" (in time_zone, default the calendar's own) or a date
    "2026-11-03" for an all-day event (end is the day after the last day).
    Without attendees it's created straight away. With attendees Google emails them invitations,
    so the first call (confirm=false) only previews: show it to the user, and call again with
    confirm=true once they agree."""
    body = {"summary": summary, "start": _when(start, time_zone, calendar_id), "end": _when(end, time_zone, calendar_id)}
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
        if not confirm:
            return send_guard.preview("calendar_create_event", body)
        send_guard.confirm("calendar_create_event", body)
    created = calendar_client.insert_event(calendar_id, body, send_updates="all" if attendees else "none")
    return _event_view(created)


@google_mcp.tool(annotations=SEND)
def calendar_update_event(
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    time_zone: str | None = None,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
    confirm: bool = False,
) -> dict:
    """Change an event; only the fields given change. Times work as in calendar_create_event.

    If the event has guests, Google emails them the change, so the first call (confirm=false)
    only previews: show it to the user, and call again with confirm=true once they agree."""
    patch = {k: v for k, v in {"summary": summary, "description": description, "location": location}.items() if v is not None}
    if start:
        patch["start"] = _when(start, time_zone, calendar_id)
    if end:
        patch["end"] = _when(end, time_zone, calendar_id)
    if not patch:
        raise ToolError("Nothing to change; give at least one field")
    guests = [a.get("email") for a in calendar_client.get_event(calendar_id, event_id).get("attendees", [])]
    if guests:
        details = {"event_id": event_id, "changes": patch, "notifies": guests}
        if not confirm:
            return send_guard.preview("calendar_update_event", details)
        send_guard.confirm("calendar_update_event", details)
    updated = calendar_client.patch_event(calendar_id, event_id, patch, send_updates="all" if guests else "none")
    return _event_view(updated)


@google_mcp.tool(annotations=DESTRUCTIVE)
def calendar_delete_event(event_id: str, calendar_id: str = "primary", confirm: bool = False) -> dict:
    """Delete an event. If it has guests, Google emails them a cancellation, so the first call
    (confirm=false) only previews: show it to the user, and call again with confirm=true once
    they agree."""
    event = calendar_client.get_event(calendar_id, event_id)
    guests = [a.get("email") for a in event.get("attendees", [])]
    if guests:
        details = {"event": _event_view(event), "cancellation_to": guests}
        if not confirm:
            return send_guard.preview("calendar_delete_event", details)
        send_guard.confirm("calendar_delete_event", details)
    calendar_client.delete_event(calendar_id, event_id, send_updates="all" if guests else "none")
    return {"deleted": event_id, "summary": event.get("summary")}
