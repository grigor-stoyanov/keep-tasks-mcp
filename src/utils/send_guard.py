"""Confirm-before-send: anything that emails other people takes two calls.

The first call (confirm=false) returns exactly what would go out and remembers a fingerprint of it.
The second (confirm=true) only goes through if that same content was previewed in the last
CONFIRM_WINDOW_SECONDS, so the model can't send something the user wasn't shown, or change a draft
between showing it and sending it. The send tools are also annotated as destructive, so AI apps
ask the user before running them.
"""
import hashlib
import json
import threading
import time

from fastmcp.exceptions import ToolError

CONFIRM_WINDOW_SECONDS = 15 * 60
ASK_USER = (
    "Nothing was sent. Show the user this preview and ask whether to send it. Only call again with "
    "confirm=true after the user explicitly says yes in their own message."
)


class SendGuard:
    def __init__(self):
        # In memory: both servers run as one instance. A restart only means previewing again.
        self._previews: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(action: str, details: dict) -> str:
        return hashlib.sha256(json.dumps([action, details], sort_keys=True, default=str).encode()).hexdigest()

    def preview(self, action: str, details: dict) -> dict:
        now = time.time()
        with self._lock:
            self._previews = {k: t for k, t in self._previews.items() if now - t < CONFIRM_WINDOW_SECONDS}
            self._previews[self._fingerprint(action, details)] = now
        return {"sent": False, "needs_confirmation": True, "preview": details, "next": ASK_USER}

    def confirm(self, action: str, details: dict) -> None:
        """Raises unless this exact content was previewed recently. Each preview allows one send."""
        with self._lock:
            previewed_at = self._previews.pop(self._fingerprint(action, details), None)
        if previewed_at is None or time.time() - previewed_at > CONFIRM_WINDOW_SECONDS:
            raise ToolError(
                "Not sent: this exact content wasn't previewed in the last 15 minutes, or it changed "
                "since. Call again with confirm=false, show the user the preview and ask them."
            )


send_guard = SendGuard()
