import os
import threading

from fastmcp.exceptions import ToolError
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from constants.calendar_consts import CALENDAR_SCOPES

REQUIRED_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")


class CalendarClient:
    """Thin wrapper around the Google Calendar API.

    Every method performs exactly ONE API call with the parameters it is given and returns
    the raw response. Paging, validation and response shaping are the caller's job.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._service = None

    def _build_service(self):
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise ToolError(f"Google Calendar is not configured; missing env vars: {', '.join(missing)}")
        creds = Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=CALENDAR_SCOPES,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def _execute(self, make_request):
        """Run one API request while holding the lock (the service is not thread-safe)."""
        with self._lock:
            if self._service is None:
                self._service = self._build_service()
            try:
                return make_request(self._service).execute()
            except RefreshError as e:
                raise ToolError(f"Google Calendar access not granted ({e}); re-run `make env` to sign in with the Calendar scope")
            except HttpError as e:
                raise ToolError(f"Google Calendar API error: {e}")

    def list_calendars(self, **params) -> dict:
        return self._execute(lambda svc: svc.calendarList().list(**params))

    def get_calendar(self, calendar_id: str) -> dict:
        return self._execute(lambda svc: svc.calendars().get(calendarId=calendar_id))

    def list_events(self, calendar_id: str, **params) -> dict:
        return self._execute(lambda svc: svc.events().list(calendarId=calendar_id, **params))

    def get_event(self, calendar_id: str, event_id: str) -> dict:
        return self._execute(lambda svc: svc.events().get(calendarId=calendar_id, eventId=event_id))

    def insert_event(self, calendar_id: str, body: dict, send_updates: str) -> dict:
        return self._execute(lambda svc: svc.events().insert(calendarId=calendar_id, body=body, sendUpdates=send_updates))

    def patch_event(self, calendar_id: str, event_id: str, body: dict, send_updates: str) -> dict:
        return self._execute(
            lambda svc: svc.events().patch(calendarId=calendar_id, eventId=event_id, body=body, sendUpdates=send_updates)
        )

    def delete_event(self, calendar_id: str, event_id: str, send_updates: str) -> None:
        self._execute(lambda svc: svc.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates=send_updates))


calendar_client = CalendarClient()
