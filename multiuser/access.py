"""Who may use which tools, and how often.

The owner gets every tool with no limits. Friends on the allowlist get FRIEND_SERVICES and
FRIEND_DAILY_CALLS successful tool calls per day. Anyone else is turned away at sign-in (auth.py).
Within that, a user only sees the tools of services they actually granted or linked.
"""
from datetime import datetime, timezone

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware
from key_value.aio.protocols.key_value import AsyncKeyValue

from constants.gmail_consts import GMAIL_SCOPES
from constants.task_consts import TASKS_SCOPES
from settings import SERVICES, Settings

USAGE_TTL = 2 * 24 * 3600  # a day's counter only needs to outlive that day
# Shown to users who haven't linked Outlook, instead of the whole outlook_* set
OUTLOOK_LINK_TOOLS = {"outlook_connect", "outlook_connect_finish"}
# Google services are optional on the consent screen; their tools need the scope to have been granted
SERVICE_SCOPES = {"tasks": TASKS_SCOPES[0], "gmail": GMAIL_SCOPES[0]}
# account_overview and friends: open to everyone allowed in, and free of the daily limit
ALWAYS_AVAILABLE = frozenset({"account"})


def allowed_services(settings: Settings, email: str) -> frozenset[str]:
    """What this person may use at all. Empty means they aren't allowed in."""
    if email and email == settings.owner_email:
        return SERVICES
    if settings.friends_enabled and email in settings.friend_emails:
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


class AccessPolicy(Middleware):
    def __init__(self, settings: Settings, store: AsyncKeyValue):
        self._settings = settings
        self._store = store

    async def on_list_tools(self, context, call_next):
        email = caller_email()
        allowed = allowed_services(self._settings, email)
        visible = allowed | ALWAYS_AVAILABLE if allowed else frozenset()
        tools = [t for t in await call_next(context) if _service(t.name) in visible and granted(_service(t.name))]
        if "outlook" in allowed and not await self._store.get(email, collection="outlook"):
            tools = [t for t in tools if _service(t.name) != "outlook" or t.name in OUTLOOK_LINK_TOOLS]
        return tools

    async def on_call_tool(self, context, call_next):
        email = caller_email()
        service = _service(context.message.name)
        allowed = allowed_services(self._settings, email)
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

        used = await self._calls_today(email)
        result = await call_next(context)
        # Only successful calls count. Refused, invalid and failing calls (Outlook not linked, bad
        # arguments, an API error) are mostly cheap and rarely the user's fault.
        await self._store.put(self.usage_key(email), {"calls": used + 1}, collection="usage", ttl=USAGE_TTL)
        return result

    @staticmethod
    def usage_key(email: str) -> str:
        return f"{email}:{datetime.now(timezone.utc).date().isoformat()}"

    async def _calls_today(self, email: str) -> int:
        """Daily per-friend budget, so friends can't run up Cloud Run or Firestore costs.

        Read-then-write, not atomic: two simultaneous calls can both pass at the limit. That
        lets through a call or two extra at worst, which is fine for a cost guard.
        """
        used = (await self._store.get(self.usage_key(email), collection="usage") or {}).get("calls", 0)
        if used >= self._settings.friend_daily_calls:
            raise ToolError(f"Daily limit of {self._settings.friend_daily_calls} tool calls reached; it resets at 00:00 UTC")
        return used
