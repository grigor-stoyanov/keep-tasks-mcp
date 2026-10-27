import os

import msal
from fastmcp.exceptions import ToolError
from outlook_personal_mcp.graph import GraphClient

from constants.outlook_consts import OUTLOOK_AUTHORITY, OUTLOOK_SCOPES

REQUIRED_ENV = ("OUTLOOK_CLIENT_ID", "OUTLOOK_REFRESH_TOKEN")


class OutlookTokens:
    """Microsoft Graph access tokens minted from the refresh token in OUTLOOK_REFRESH_TOKEN.

    Fills the token_provider slot of outlook_personal_mcp's GraphClient, which calls get_token()
    before every request. MSAL keeps the access token and the rotated refresh token in its
    in-memory cache, so Microsoft is only asked for a new token about once an hour.
    No lock: the Outlook tools are async, so get_token() only ever runs on the event loop thread.
    """

    def __init__(self):
        self._app = None

    def get_token(self) -> str:
        if self._app is None:
            missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
            if missing:
                raise ToolError(f"Outlook is not configured; missing env vars: {', '.join(missing)}")
            self._app = msal.PublicClientApplication(os.environ["OUTLOOK_CLIENT_ID"], authority=OUTLOOK_AUTHORITY)
        accounts = self._app.get_accounts()
        result = self._app.acquire_token_silent(OUTLOOK_SCOPES, account=accounts[0]) if accounts else None
        if not result:
            result = self._app.acquire_token_by_refresh_token(os.environ["OUTLOOK_REFRESH_TOKEN"], OUTLOOK_SCOPES)
        if "access_token" not in result:
            reason = result.get("error_description") or result.get("error")
            raise ToolError(f"Outlook sign-in failed ({reason}); re-run `make env-outlook` and redeploy")
        return result["access_token"]


# Building the GraphClient makes no network calls; the first tool call does the sign-in
outlook_graph = GraphClient(OutlookTokens())
