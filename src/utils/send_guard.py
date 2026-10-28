"""Confirm-before-send: anything that emails other people takes two calls.

The first call (confirm=false) returns exactly what would go out and remembers a fingerprint of it.
The second (confirm=true) only goes through if that same content was previewed in the last
CONFIRM_WINDOW_SECONDS, so the model can't send something the user wasn't shown, or change a draft
between showing it and sending it. The send tools are also annotated as destructive, so AI apps
ask the user before running them.

Previews belong to whoever made them: on the shared server one user's preview can't confirm
another's send. `binding` is fingerprinted but not shown, for things that identify the exact
content without being readable (a draft's message id or change key).

Bulk tools use hold() and take() instead: the dry run holds the exact items it matched under a
token, and the real run acts on those items only, never on a fresh search.
"""
import hashlib
import json
import secrets
import threading
import time

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

CONFIRM_WINDOW_SECONDS = 15 * 60
ASK_USER = (
    "Nothing was sent. Show the user this preview and ask whether to send it. Only call again with "
    "confirm=true after the user explicitly says yes in their own message."
)


def _caller() -> str:
    """Who is calling: their email on the shared server, empty on the personal one (one user)."""
    token = get_access_token()
    if token is None:
        return ""
    return str((token.claims or {}).get("email") or token.client_id or "")


class SendGuard:
    def __init__(self):
        # In memory: both servers run as one instance. A restart only means previewing again.
        self._previews: dict[str, float] = {}
        self._held: dict[str, tuple[float, str, object]] = {}  # token key -> (time, fingerprint, items)
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(action: str, details: dict, binding=None) -> str:
        payload = [_caller(), action, details, binding]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def _expire(self, now: float) -> None:
        """Caller must hold the lock."""
        self._previews = {k: t for k, t in self._previews.items() if now - t < CONFIRM_WINDOW_SECONDS}
        self._held = {k: v for k, v in self._held.items() if now - v[0] < CONFIRM_WINDOW_SECONDS}

    def preview(self, action: str, details: dict, binding=None) -> dict:
        now = time.time()
        with self._lock:
            self._expire(now)
            self._previews[self._fingerprint(action, details, binding)] = now
        return {"sent": False, "needs_confirmation": True, "preview": details, "next": ASK_USER}

    def confirm(self, action: str, details: dict, binding=None) -> None:
        """Raises unless this exact content was previewed recently. Each preview allows one send."""
        with self._lock:
            previewed_at = self._previews.pop(self._fingerprint(action, details, binding), None)
        if previewed_at is None or time.time() - previewed_at > CONFIRM_WINDOW_SECONDS:
            raise ToolError(
                "Not sent: this exact content wasn't previewed in the last 15 minutes, or it changed "
                "since. Call again with confirm=false, show the user the preview and ask them."
            )

    def hold(self, action: str, params: dict, items) -> str:
        """Keep the items a dry run matched; returns the token the real run must pass back."""
        token = secrets.token_urlsafe(8)
        now = time.time()
        with self._lock:
            self._expire(now)
            self._held[f"{_caller()}:{action}:{token}"] = (now, self._fingerprint(action, params), items)
        return token

    def take(self, action: str, params: dict, token: str | None):
        """The items held by that dry run, if it was for these same params. Each token works once."""
        if not token:
            raise ToolError("Run this with dry_run=true first, show the user the result, and pass its confirm_token")
        with self._lock:
            held = self._held.pop(f"{_caller()}:{action}:{token}", None)
        if held is None or time.time() - held[0] > CONFIRM_WINDOW_SECONDS:
            raise ToolError("That confirm_token is unknown, used or older than 15 minutes; run the dry run again")
        if held[1] != self._fingerprint(action, params):
            raise ToolError("These arguments differ from the dry run's; run the dry run again with them")
        return held[2]


send_guard = SendGuard()
