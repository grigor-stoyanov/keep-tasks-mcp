"""Who may use which tools, and how often.

The owner gets every tool with no limits. Friends on the allowlist (friends.py) get FRIEND_SERVICES and
FRIEND_DAILY_CALLS successful tool calls per day. Anyone else is turned away at sign-in (auth.py).
Within that, a user only sees the tools of services they actually granted or linked.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware
from key_value.aio.protocols.key_value import AsyncKeyValue

from constants.calendar_consts import CALENDAR_SCOPES
from constants.gmail_consts import GMAIL_SCOPES
from constants.task_consts import TASKS_SCOPES
from friends import Friends
from settings import SERVICES, Settings

log = logging.getLogger(__name__)

USAGE_TTL = 2 * 24 * 3600  # a day's counter only needs to outlive that day
# Shown to users who haven't linked Outlook, instead of the whole outlook_* set
OUTLOOK_LINK_TOOLS = {"outlook_connect", "outlook_connect_finish"}
# Google services are optional on the consent screen; their tools need the scope to have been granted
SERVICE_SCOPES = {"tasks": TASKS_SCOPES[0], "gmail": GMAIL_SCOPES[0], "calendar": CALENDAR_SCOPES[0]}
# Services that sign in with the owner's env credentials rather than the caller's, and need them set
SERVICE_ENV = {"keep": ("KEEP_EMAIL", "KEEP_MASTER_TOKEN")}
# account_overview and friends: open to everyone allowed in, and free of the daily limit
ALWAYS_AVAILABLE = frozenset({"account"})


async def allowed_services(settings: Settings, friends: Friends, email: str, fresh: bool = False) -> frozenset[str]:
    """What this person may use at all. Empty means they aren't allowed in.

    fresh=True reads the allowlist from the store instead of the cache, so a removal made on
    another instance (during a redeploy) takes effect at once."""
    if email and email == settings.owner_email:
        return SERVICES
    if settings.friends_enabled and await friends.contains(email, fresh=fresh):
        return settings.friend_services
    return frozenset()


def caller_email() -> str:
    token = get_access_token()
    return str((token.claims or {}).get("email") or "").lower() if token else ""


def _service(tool_name: str) -> str:
    return tool_name.split("_", 1)[0]


def granted(service: str) -> bool:
    scope = SERVICE_SCOPES.get(service)
    token = get_access_token()
    return scope is None or (token is not None and scope in token.scopes)


def configured(service: str) -> bool:
    return all(os.environ.get(name) for name in SERVICE_ENV.get(service, ()))


class AccessPolicy(Middleware):
    def __init__(self, settings: Settings, store: AsyncKeyValue, friends: Friends):
        self._settings = settings
        self._store = store
        self._friends = friends
        # Counter updates are read-then-write on a plain key-value store; with one instance
        # (--max-instances 1) this lock makes them atomic
        self._usage_lock = asyncio.Lock()

    async def on_list_tools(self, context, call_next):
        email = caller_email()
        allowed = await allowed_services(self._settings, self._friends, email)
        visible = allowed | ALWAYS_AVAILABLE if allowed else frozenset()
        tools = [
            t for t in await call_next(context)
            if _service(t.name) in visible and granted(_service(t.name)) and configured(_service(t.name))
        ]
        if "outlook" in allowed and not await self._store.get(email, collection="outlook"):
            tools = [t for t in tools if _service(t.name) != "outlook" or t.name in OUTLOOK_LINK_TOOLS]
        return tools

    async def on_call_tool(self, context, call_next):
        email = caller_email()
        service = _service(context.message.name)
        allowed = await allowed_services(self._settings, self._friends, email, fresh=True)
        if not allowed:
            raise ToolError(f"{email or 'This account'} isn't on this server's allowlist; ask {self._settings.owner_email} to add you")
        if service not in allowed | ALWAYS_AVAILABLE:
            raise ToolError(f"{context.message.name} isn't shared with your account")
        if not granted(service):
            raise ToolError(
                f"You didn't allow {service} access when signing in. To add it, remove and re-add this "
                f"connector in your AI app and tick {service} on Google's consent screen."
            )
        if email == self._settings.owner_email or service in ALWAYS_AVAILABLE:
            return await call_next(context)

        # The day is fixed once, so a call that runs past midnight is charged and refunded on the same day
        key = self.usage_key(email)
        await self._reserve(key)
        try:
            return await call_next(context)
        except Exception:
            # Only successful calls count. Refused, invalid and failing calls (Outlook not linked, bad
            # arguments, an API error) are mostly cheap and rarely the user's fault.
            await self._refund(key)
            raise

    @staticmethod
    def usage_key(email: str) -> str:
        return f"{email}:{datetime.now(timezone.utc).date().isoformat()}"

    async def _reserve(self, key: str) -> None:
        """Daily per-friend budget, so friends can't run up Cloud Run or Firestore costs.

        The call is counted before it runs, so overlapping calls can't all slip in under the limit,
        and nothing has to be written after an action that already happened.
        """
        async with self._usage_lock:
            used = (await self._store.get(key, collection="usage") or {}).get("calls", 0)
            if used >= self._settings.friend_daily_calls:
                raise ToolError(f"Daily limit of {self._settings.friend_daily_calls} tool calls reached; it resets at 00:00 UTC")
            await self._store.put(key, {"calls": used + 1}, collection="usage", ttl=USAGE_TTL)

    async def _refund(self, key: str) -> None:
        # Best effort: failing here must not hide the tool's own error, it only costs the user one call
        try:
            async with self._usage_lock:
                used = (await self._store.get(key, collection="usage") or {}).get("calls", 0)
                await self._store.put(key, {"calls": max(0, used - 1)}, collection="usage", ttl=USAGE_TTL)
        except Exception:
            log.warning("Couldn't refund a failed call on %s", key, exc_info=True)
