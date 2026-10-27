import os
import threading
import time

from fastmcp.exceptions import ToolError
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from constants.gmail_consts import GMAIL_SCOPES

REQUIRED_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
# Gmail's per-user quota is counted per minute, so back off for up to ~1 minute before giving up
RATE_LIMIT_DELAYS = (2, 4, 8, 16, 32)


def _is_rate_limited(e: HttpError) -> bool:
    return e.resp.status == 429 or (e.resp.status == 403 and "ratelimitexceeded" in str(e).lower())


class GmailClient:
    """Thin wrapper around the Gmail API.

    Every method performs exactly ONE HTTP call with the parameters it is given and returns
    the raw response. Paging, chunking, retries and response shaping are the caller's job.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._service = None

    def _build_service(self):
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise ToolError(f"Gmail is not configured; missing env vars: {', '.join(missing)}")
        creds = Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=GMAIL_SCOPES,
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def _execute(self, make_request):
        """Run one API request while holding the lock (the service is not thread-safe).

        make_request receives the service and returns an un-executed request, e.g.
        lambda svc: svc.users().messages().list(userId="me")
        """
        with self._lock:
            if self._service is None:
                self._service = self._build_service()
            for delay in (*RATE_LIMIT_DELAYS, None):
                try:
                    return make_request(self._service).execute()
                except RefreshError as e:
                    raise ToolError(f"Gmail access not granted ({e}); re-run `make env` to sign in with the Gmail scope")
                except HttpError as e:
                    if delay is None or not _is_rate_limited(e):
                        raise ToolError(f"Gmail API error: {e}")
                    time.sleep(delay)

    def list_messages(self, **params) -> dict:
        return self._execute(lambda svc: svc.users().messages().list(userId="me", **params))

    def batch_modify(self, body: dict) -> None:
        self._execute(lambda svc: svc.users().messages().batchModify(userId="me", body=body))

    def get_message(self, msg_id: str, **params) -> dict:
        return self._execute(lambda svc: svc.users().messages().get(userId="me", id=msg_id, **params))

    def list_drafts(self, **params) -> dict:
        return self._execute(lambda svc: svc.users().drafts().list(userId="me", **params))

    def get_draft(self, draft_id: str, **params) -> dict:
        return self._execute(lambda svc: svc.users().drafts().get(userId="me", id=draft_id, **params))

    def create_draft(self, body: dict) -> dict:
        return self._execute(lambda svc: svc.users().drafts().create(userId="me", body=body))

    def send_draft(self, draft_id: str) -> dict:
        return self._execute(lambda svc: svc.users().drafts().send(userId="me", body={"id": draft_id}))

    def get_metadata(self, ids: list[str], headers: list[str]) -> tuple[list[dict], list[str]]:
        """Fetch the given headers of many messages in one batch HTTP request.

        Returns (messages, failed_ids). A sub-request can fail on its own (usually
        rateLimitExceeded) without failing the batch; those ids are returned for the caller to retry.
        """
        messages, failed = [], []

        def on_response(request_id, response, exception):
            if exception is None:
                messages.append(response)
            else:
                failed.append(request_id)

        def make_batch(svc):
            batch = svc.new_batch_http_request(callback=on_response)
            for msg_id in ids:
                batch.add(
                    svc.users().messages().get(
                        userId="me", id=msg_id, format="metadata", metadataHeaders=headers,
                        fields="id,threadId,labelIds,snippet,internalDate,payload/headers",
                    ),
                    request_id=msg_id,
                )
            return batch

        self._execute(make_batch)
        return messages, failed


gmail_client = GmailClient()
