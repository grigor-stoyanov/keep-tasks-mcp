"""Telling friends what they can do: the account_overview tool, a getting_started prompt, the
server instructions, the public /join page they open from the invite link (share.py), and
/add-to-claude, a one-click link that opens Claude's Add connector dialog already filled in.

Features come from the one catalogue in invite.py, so the page, the invite and what the AI says
stay in sync.
"""
from fastmcp.exceptions import ToolError
from key_value.aio.protocols.key_value import AsyncKeyValue
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from access import AccessPolicy, allowed_services, caller_email, granted
from constants.tool_annotations import READ
from invite import FEATURES, claude_install_link, join_page
from server import google_mcp
from settings import Settings

INSTRUCTIONS = (
    "This is a shared server: each user has their own set of features. The first time the user "
    "uses it in a conversation, or asks what it can do, call account_overview and tell them in a "
    "few friendly lines which features they have, with an example request or two for each. Tools "
    "for services they haven't enabled are hidden; account_overview says how to enable them."
)


def register(settings: Settings, store: AsyncKeyValue) -> None:
    google_mcp.instructions = f"{google_mcp.instructions} {INSTRUCTIONS}"

    @google_mcp.tool(annotations=READ)
    async def account_overview() -> dict:
        """What this user can do with the connector: their features with example requests,
        services they could still enable and how, and their usage today. Call it when the user
        first connects or asks what this can do, then explain it to them in plain words."""
        email = caller_email()
        allowed = allowed_services(settings, email)
        if not allowed:
            raise ToolError(f"{email or 'This account'} isn't on this server's allowlist; ask {settings.owner_email} to add you")
        outlook_linked = bool(await store.get(email, collection="outlook"))

        available, can_enable = [], []
        for service in sorted(allowed):
            feature = {"service": service, **FEATURES[service]}
            if not granted(service):
                can_enable.append({**feature, "how": f"Remove and re-add the connector, and tick {feature['title']} on Google's consent screen"})
            elif service == "outlook" and not outlook_linked:
                can_enable.append({**feature, "how": "Ask: \"Connect my Outlook\""})
            else:
                available.append(feature)

        overview = {"signed_in_as": email, "available": available, "can_enable": can_enable, "owner_contact": settings.owner_email}
        if email != settings.owner_email:
            used = (await store.get(AccessPolicy.usage_key(email), collection="usage") or {}).get("calls", 0)
            overview["tool_calls_today"] = f"{used} of {settings.friend_daily_calls} (resets at 00:00 UTC)"
        return overview

    @google_mcp.prompt
    def getting_started() -> str:
        """A short tour of what this connector can do for you."""
        return (
            "Call account_overview, then give me a short, friendly tour of what I can do with this "
            "connector: one line per feature I have, with two example requests I could try. "
            "Mention anything I could still enable and how."
        )

    @google_mcp.custom_route("/", methods=["GET"])
    async def home(request: Request) -> RedirectResponse:
        return RedirectResponse("/join")

    @google_mcp.custom_route("/add-to-claude", methods=["GET"])
    async def add_to_claude(request: Request) -> RedirectResponse:
        return RedirectResponse(claude_install_link(settings.public_url))

    @google_mcp.custom_route("/join", methods=["GET"])
    async def join(request: Request) -> HTMLResponse:
        return HTMLResponse(join_page(settings.public_url, settings.owner_email, settings.friend_services))
