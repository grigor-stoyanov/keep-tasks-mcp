"""Tools for linking a user's Outlook.com account to their Google sign-in.

Sign-in to the server is Google only, so Outlook is linked separately, once, with Microsoft's
device-code flow: the user opens a link, enters a code, and the model then calls outlook_connect_finish.
"""
from access import caller_email
from constants.tool_annotations import WRITE
from per_user import OutlookAccounts
from server import google_mcp


def register(accounts: OutlookAccounts) -> None:
    @google_mcp.tool(annotations=WRITE)
    async def outlook_connect() -> dict:
        """Start linking the user's Outlook.com account (mail, calendar and Microsoft To Do).

        Also use it when an Outlook tool says the sign-in needs new permissions.

        Show the user the link and code from the response. After they say they have signed in,
        call outlook_connect_finish."""
        flow = await accounts.start_connect(caller_email())
        return {
            "open_this_link": flow["verification_uri"],
            "enter_this_code": flow["user_code"],
            "expires_in_minutes": int(flow.get("expires_in", 900)) // 60,
        }

    @google_mcp.tool(annotations=WRITE)
    async def outlook_connect_finish() -> dict:
        """Finish linking Outlook after the user has entered the code from outlook_connect."""
        if await accounts.finish_connect(caller_email()):
            # The tool list only refreshes when a chat starts, so the Outlook tools appear in the next one
            return {"linked": True, "next": "Tell the user to start a new chat to use their Outlook tools."}
        return {"linked": False, "hint": "The code hasn't been entered yet. Ask the user to finish, then call this again."}

    @google_mcp.tool(annotations=WRITE)
    async def outlook_disconnect() -> dict:
        """Unlink the user's Outlook account and delete its stored token from this server."""
        return {"unlinked": await accounts.disconnect(caller_email())}
