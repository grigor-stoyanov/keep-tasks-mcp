"""Owner-only tools for managing who can use the shared server, from any chat, without a redeploy.

AccessPolicy already hides the friends_* tools from everyone but the owner (they're an owner-only
service in settings.py); _owner_only() checks again so a policy mistake can't hand them out.
"""
from fastmcp.exceptions import ToolError
from key_value.aio.protocols.key_value import AsyncKeyValue

from access import AccessPolicy, caller_email
from constants.tool_annotations import DESTRUCTIVE, READ, WRITE
from friends import Friends
from invite import invite_message
from per_user import OutlookAccounts
from server import google_mcp
from settings import MAX_FRIENDS, Settings


def register(friends: Friends, accounts: OutlookAccounts, settings: Settings, store: AsyncKeyValue) -> None:
    def _owner_only() -> None:
        if caller_email() != settings.owner_email:
            raise ToolError("Only the owner can manage friends")

    @google_mcp.tool(annotations=READ)
    async def friends_list() -> dict:
        """Everyone who can use this server: when they were added, whether they linked Outlook,
        and their tool calls today. Owner only."""
        _owner_only()
        people = []
        for email, info in sorted((await friends.all()).items()):
            usage = await store.get(AccessPolicy.usage_key(email), collection="usage") or {}
            people.append({
                "email": email,
                "added": info.get("added"),
                "outlook_linked": bool(await store.get(email, collection="outlook")),
                "tool_calls_today": usage.get("calls", 0),
            })
        return {
            "friends": people,
            "slots": f"{len(people)} of {MAX_FRIENDS}",
            "daily_limit_each": settings.friend_daily_calls,
            "friends_enabled": settings.friends_enabled,
        }

    @google_mcp.tool(annotations=WRITE)
    async def friends_add(email: str, name: str = "") -> dict:
        """Let someone use this server with their Google account. Owner only.

        Returns an invite to send them: show it to the user exactly as written so they can copy it.
        `name` is the friend's first name for the greeting."""
        _owner_only()
        added = await friends.add(email)
        result = {
            "email": email.strip().lower(),
            "status": "added" if added else "already a friend",
            "slots": f"{len(await friends.all())} of {MAX_FRIENDS}",
            "invite": invite_message(settings.public_url, settings.owner_email, settings.friend_services,
                                     settings.friend_daily_calls, name),
        }
        if not settings.friends_enabled:
            result["warning"] = "FRIENDS_ENABLED is false, so no friend can use the server until it's turned back on"
        return result

    @google_mcp.tool(annotations=DESTRUCTIVE)
    async def friends_remove(email: str) -> dict:
        """Take away someone's access. Owner only.

        They're cut off at once, and their linked Outlook token is deleted from this server. Their
        Google sign-in stays stored but is refused; they can remove the app from their Google account."""
        _owner_only()
        email = email.strip().lower()
        if not await friends.remove(email):
            return {"email": email, "status": "wasn't a friend", "slots": f"{len(await friends.all())} of {MAX_FRIENDS}"}
        await accounts.disconnect(email)
        return {"email": email, "status": "removed", "slots": f"{len(await friends.all())} of {MAX_FRIENDS}"}
