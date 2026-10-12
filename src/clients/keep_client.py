import os
import threading

import gkeepapi
from fastmcp.exceptions import ToolError


class KeepClient:
    """Thin wrapper around gkeepapi.

    Each method is a single gkeepapi call made under a lock, returning exactly what gkeepapi
    returns. Changing a note, checking that it exists and shaping the response are the tool's job;
    when the tool is done changing nodes it calls sync() to push them.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._keep = None  # authenticated on first use

    def _authenticate(self) -> gkeepapi.Keep:
        email, token = os.environ.get("KEEP_EMAIL"), os.environ.get("KEEP_MASTER_TOKEN")
        if not (email and token):
            raise ToolError("Google Keep is not configured; set KEEP_EMAIL and KEEP_MASTER_TOKEN")
        keep = gkeepapi.Keep()
        try:
            keep.authenticate(email, token)  # also does the first sync
        except Exception as e:
            raise ToolError(f"Google Keep login failed: {e}")
        return keep

    def _connect(self) -> gkeepapi.Keep:
        """Authenticate on first use, otherwise pull the latest changes. Caller must hold the lock."""
        if self._keep is None:
            self._keep = self._authenticate()
        else:
            self._keep.sync()
        return self._keep

    def get(self, note_id: str):
        with self._lock:
            return self._connect().get(note_id)

    def find(self, **params) -> list:
        with self._lock:
            return list(self._connect().find(**params))

    def find_label(self, name: str, create: bool = False):
        with self._lock:
            return self._connect().findLabel(name, create=create)

    def create_note(self, title: str, text: str = ""):
        with self._lock:
            return self._connect().createNote(title, text)

    def create_list(self, title: str, items: list[tuple[str, bool]]):
        with self._lock:
            return self._connect().createList(title, items)

    def sync(self) -> None:
        """Push local changes made to nodes returned by the methods above."""
        with self._lock:
            self._keep.sync()


keep_client = KeepClient()
