# calendar.events reads and writes events on every calendar the user has; calendar.readonly is only
# for listing the calendars themselves. Neither can delete or share whole calendars.
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]
MAX_EVENTS = 250  # events.list maxResults
