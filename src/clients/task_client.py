import os
import threading

from fastmcp.exceptions import ToolError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from constants.task_consts import TASKS_SCOPES

REQUIRED_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")


class TaskClient:
    """Thin wrapper around the Google Tasks API.

    Every method performs exactly ONE API call with the parameters it is given and returns
    the raw response. Paging, validation and response shaping are the caller's job.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._service = None

    def _build_service(self):
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise ToolError(f"Google Tasks is not configured; missing env vars: {', '.join(missing)}")
        creds = Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=TASKS_SCOPES,
        )
        return build("tasks", "v1", credentials=creds, cache_discovery=False)

    def _execute(self, make_request):
        """Run one API request while holding the lock (the service is not thread-safe).

        make_request receives the service and returns an un-executed request, e.g.
        lambda svc: svc.tasks().list(tasklist="@default")
        """
        with self._lock:
            if self._service is None:
                self._service = self._build_service()
            try:
                return make_request(self._service).execute()
            except HttpError as e:
                raise ToolError(f"Google Tasks API error: {e}")



    def list_tasklists(self, **params) -> dict:
        return self._execute(lambda svc: svc.tasklists().list(**params))

    def create_tasklist(self, body: dict) -> dict:
        return self._execute(lambda svc: svc.tasklists().insert(body=body))

    def list_tasks(self, tasklist: str, **params) -> dict:
        return self._execute(lambda svc: svc.tasks().list(tasklist=tasklist, **params))

    def create_task(self, tasklist: str, body: dict, parent: str | None = None) -> dict:
        return self._execute(lambda svc: svc.tasks().insert(tasklist=tasklist, body=body, parent=parent))

    def patch_task(self, tasklist: str, task: str, body: dict) -> dict:
        return self._execute(lambda svc: svc.tasks().patch(tasklist=tasklist, task=task, body=body))

    def delete_task(self, tasklist: str, task: str) -> None:
        self._execute(lambda svc: svc.tasks().delete(tasklist=tasklist, task=task))


task_client = TaskClient()
