"""Per-caller versions of the src/ clients, so the src/ tools work unchanged for every user.

The src/ tools call module-level singletons (task_client, gmail_client, outlook_graph) that sign
in with the owner's env credentials. install() replaces each one with a subclass that uses the
credentials of whoever is calling. It must run before the tool modules are imported, because they
bind the singletons with `from clients.x import y` at import time.

Keep is left alone: it stays on the owner's env credentials and access.py keeps friends away from it.
"""
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar

import anyio
import msal
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from key_value.aio.protocols.key_value import AsyncKeyValue
from outlook_personal_mcp.graph import GraphClient

import clients.calendar_client
import clients.gmail_client
import clients.outlook_client
import clients.task_client
from access import caller_email
from constants.outlook_consts import OUTLOOK_AUTHORITY, OUTLOOK_SCOPES
from settings import Settings

SERVICE_CACHE_SIZE = 20  # built Google API services, one per live access token


def _contact(owner_email: str) -> str:
    return f"If that doesn't help, contact {owner_email}."


class _CallerService:
    """Mixin for the src/ Google clients: points their cached service at the caller before each call.

    The base _execute builds self._service once and reuses it. Here it is swapped for the caller's
    service on every call, under a separate lock, because the base class takes self._lock itself
    inside _execute.
    """

    api: tuple[str, str]

    def __init__(self, owner_email: str):
        super().__init__()
        self._owner_email = owner_email
        self._caller_lock = threading.Lock()
        self._services: OrderedDict[str, object] = OrderedDict()

    def _execute(self, make_request):
        token = get_access_token()
        if token is None:
            raise ToolError("Not signed in")
        with self._caller_lock:
            self._service = self._service_for(token.token)
            try:
                return super()._execute(make_request)
            except RefreshError as e:
                raise self._sign_in_expired() from e
            except ToolError as e:
                # GmailClient turns RefreshError into its own owner-facing ToolError ("re-run make env")
                if isinstance(e.__context__, RefreshError):
                    raise self._sign_in_expired() from e
                raise

    def _sign_in_expired(self) -> ToolError:
        # Google rejected an access token the sign-in proxy believed was valid, i.e. it was revoked
        return ToolError(
            "Your Google sign-in has expired or was revoked. Reconnect this connector in your AI app's "
            f"settings. {_contact(self._owner_email)}"
        )

    def _service_for(self, access_token: str):
        # The sign-in proxy refreshes Google tokens itself, so a plain access token is enough here
        service = self._services.pop(access_token, None) or build(
            *self.api, credentials=Credentials(access_token), cache_discovery=False
        )
        self._services[access_token] = service
        while len(self._services) > SERVICE_CACHE_SIZE:
            self._services.popitem(last=False)
        return service


class CallerTaskClient(_CallerService, clients.task_client.TaskClient):
    api = ("tasks", "v1")


class CallerGmailClient(_CallerService, clients.gmail_client.GmailClient):
    api = ("gmail", "v1")


class CallerCalendarClient(_CallerService, clients.calendar_client.CalendarClient):
    api = ("calendar", "v3")


class OutlookAccounts:
    """Each user's Microsoft refresh token, kept in the encrypted store under their Google email.

    Users link Outlook once with the device-code flow (connect_tools.py). Pending sign-ins live in
    memory, which is fine with --max-instances 1; a restart just means calling outlook_connect again.
    """

    def __init__(self, store: AsyncKeyValue, client_id: str, owner_email: str):
        self._store = store
        self._client_id = client_id
        self._owner_email = owner_email
        self._app = None
        self._access: dict[str, tuple[str, float]] = {}  # email -> (access token, expires at)
        self._pending: dict[str, dict] = {}  # email -> device flow waiting for the user

    def _msal(self) -> msal.PublicClientApplication:
        if not self._client_id:
            raise ToolError(f"Outlook isn't set up on this server yet; contact {self._owner_email}")
        if self._app is None:
            self._app = msal.PublicClientApplication(self._client_id, authority=OUTLOOK_AUTHORITY)
        return self._app

    async def access_token(self, email: str) -> str:
        cached = self._access.get(email)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        stored = await self._store.get(email, collection="outlook")
        if not stored:
            raise ToolError("Outlook isn't linked to your account yet; call outlook_connect first")
        result = await anyio.to_thread.run_sync(
            self._msal().acquire_token_by_refresh_token, stored["refresh_token"], OUTLOOK_SCOPES
        )
        return await self._save(email, result)

    async def _save(self, email: str, result: dict) -> str:
        if "access_token" not in result:
            reason = result.get("error_description") or result.get("error")
            raise ToolError(
                f"Your Outlook sign-in has expired or was revoked ({reason}). Call outlook_connect to "
                f"link it again. {_contact(self._owner_email)}"
            )
        # Microsoft rotates refresh tokens, so store the newest one to keep the 90-day window sliding
        if result.get("refresh_token"):
            await self._store.put(email, {"refresh_token": result["refresh_token"]}, collection="outlook")
        self._access[email] = (result["access_token"], time.time() + int(result.get("expires_in", 3600)))
        return result["access_token"]

    async def start_connect(self, email: str) -> dict:
        flow = await anyio.to_thread.run_sync(self._msal().initiate_device_flow, OUTLOOK_SCOPES)
        if "user_code" not in flow:
            raise ToolError(f"Couldn't start the Microsoft sign-in: {flow.get('error_description', flow)}")
        self._pending[email] = flow
        return flow

    async def finish_connect(self, email: str) -> bool:
        """True once linked, False while the user still has to enter the code."""
        flow = self._pending.get(email)
        if flow is None:
            raise ToolError("No Outlook sign-in in progress; call outlook_connect first")
        # exit_condition makes MSAL poll Microsoft once instead of blocking until the code expires
        result = await anyio.to_thread.run_sync(
            lambda: self._msal().acquire_token_by_device_flow(flow, exit_condition=lambda _: True)
        )
        if result.get("error") in ("authorization_pending", "slow_down"):
            return False
        del self._pending[email]
        await self._save(email, result)
        return True

    async def disconnect(self, email: str) -> bool:
        self._access.pop(email, None)
        return await self._store.delete(email, collection="outlook")


# GraphClient asks its token provider synchronously, but the caller's refresh token lives in the
# async store, so CallerOutlookGraph fetches the access token first and hands it over through this.
_outlook_access_token: ContextVar[str] = ContextVar("outlook_access_token")


class _ContextTokens:
    def get_token(self) -> str:
        return _outlook_access_token.get()


class CallerOutlookGraph(GraphClient):
    """outlook-personal-mcp's Graph client, signed in as the caller."""

    def __init__(self, accounts: OutlookAccounts):
        super().__init__(_ContextTokens())
        self._accounts = accounts

    async def request(self, method, path, **kwargs):
        _outlook_access_token.set(await self._accounts.access_token(caller_email()))
        return await super().request(method, path, **kwargs)


def install(store: AsyncKeyValue, settings: Settings) -> OutlookAccounts:
    """Swap the src/ client singletons for per-caller ones. Call before importing any tool module."""
    clients.task_client.task_client = CallerTaskClient(settings.owner_email)
    clients.gmail_client.gmail_client = CallerGmailClient(settings.owner_email)
    clients.calendar_client.calendar_client = CallerCalendarClient(settings.owner_email)
    accounts = OutlookAccounts(store, settings.outlook_client_id, settings.owner_email)
    clients.outlook_client.outlook_graph = CallerOutlookGraph(accounts)
    return accounts
