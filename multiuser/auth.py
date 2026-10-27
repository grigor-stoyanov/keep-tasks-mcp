"""Google sign-in for the shared server, and the encrypted store that keeps everyone's tokens."""
import base64
import json

from fastmcp.server.auth.oauth_proxy.models import HTTP_TIMEOUT_SECONDS
from fastmcp.server.auth.oauth_proxy.upstream import AsyncOAuth2Client
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.protocols.key_value import AsyncKeyValue
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from access import allowed_services
from friends import Friends
from constants.gmail_consts import GMAIL_SCOPES
from constants.task_consts import TASKS_SCOPES
from settings import Settings

# Only these are required. Tasks and Gmail are asked for on the same consent screen, but people can
# untick them; access.py then hides the tools of any service whose scope wasn't granted.
REQUIRED_SCOPES = ["openid", "email"]
REQUESTED_SCOPES = [*REQUIRED_SCOPES, *TASKS_SCOPES, *GMAIL_SCOPES]
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def build_store(settings: Settings) -> AsyncKeyValue:
    """Firestore in production (free tier, survives Cloud Run restarts), memory for local tests.

    FastMCP only encrypts the default store it creates itself, so a store passed in is wrapped
    here. It holds Google and Microsoft refresh tokens, so it must never be stored in plain text.
    """
    if settings.store == "memory":
        from key_value.aio.stores.memory import MemoryStore

        backend = MemoryStore()
    else:
        from key_value.aio.stores.firestore.store import (
            FirestoreStore,
            FirestoreV1CollectionSanitizationStrategy,
            FirestoreV1KeySanitizationStrategy,
        )

        # Keys can contain "/", which Firestore document ids can't: ChatGPT and Claude register as
        # OAuth clients whose id is a URL (https://chatgpt.com/oauth/client.json). Valid keys are kept as-is.
        backend = FirestoreStore(
            default_collection="keep-tasks-mcp",
            key_sanitization_strategy=FirestoreV1KeySanitizationStrategy(),
            collection_sanitization_strategy=FirestoreV1CollectionSanitizationStrategy(),
        )
    return FernetEncryptionWrapper(backend, source_material=settings.server_key, salt="keep-tasks-mcp-store")


class SignInRejected(Exception):
    """Raised from the code exchange; FastMCP shows its message on the sign-in error page."""


def _id_token_email(tokens: dict) -> str:
    """The verified email in the ID token. It comes straight from Google's token endpoint over
    TLS, which OpenID Connect accepts in place of checking the signature."""
    try:
        payload = tokens["id_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (KeyError, IndexError, ValueError):
        return ""
    return str(claims.get("email", "")).lower() if claims.get("email_verified") else ""


class _AllowlistOAuthClient(AsyncOAuth2Client):
    """Checks the allowlist right after Google hands over the tokens.

    FastMCP stores the tokens as soon as this returns, so rejecting here, and revoking them, means
    nothing of a stranger's is ever kept. Refreshes go through refresh_token() and aren't checked:
    only people who passed this check have refresh tokens to begin with.
    """

    def __init__(self, *args, settings: Settings, friends: Friends, **kwargs):
        super().__init__(*args, **kwargs)
        self._settings = settings
        self._friends = friends

    async def fetch_token(self, url, *, grant_type="authorization_code", **params):
        tokens = await super().fetch_token(url, grant_type=grant_type, **params)
        email = _id_token_email(tokens)
        if grant_type == "authorization_code" and not await allowed_services(self._settings, self._friends, email):
            await self._revoke(tokens)
            raise SignInRejected(
                f"{email or 'This Google account'} isn't on this server's allowlist. "
                f"Ask {self._settings.owner_email} to add you."
            )
        return tokens

    async def _revoke(self, tokens: dict) -> None:
        # Best effort: the tokens are dropped either way, revoking just removes the app from their account
        try:
            await self._client.post(GOOGLE_REVOKE_URL, data={"token": tokens.get("refresh_token") or tokens["access_token"]})
        except Exception:
            pass


class AllowlistGoogleProvider(GoogleProvider):
    def __init__(self, *, settings: Settings, friends: Friends, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings
        self._friends = friends

    def _create_upstream_oauth_client(self) -> AsyncOAuth2Client:
        # Same arguments as OAuthProxy._create_upstream_oauth_client, which this replaces
        return _AllowlistOAuthClient(
            client_id=self._upstream_client_id,
            client_secret=self._settings.oauth_client_secret,
            token_endpoint_auth_method=self._token_endpoint_auth_method,
            timeout=HTTP_TIMEOUT_SECONDS,
            settings=self._settings,
            friends=self._friends,
        )


def build_auth(settings: Settings, store: AsyncKeyValue, friends: Friends) -> GoogleProvider:
    return AllowlistGoogleProvider(
        settings=settings,
        friends=friends,
        client_id=settings.oauth_client_id,
        client_secret=settings.oauth_client_secret,
        base_url=settings.public_url,
        required_scopes=REQUIRED_SCOPES,
        valid_scopes=REQUESTED_SCOPES,
        # Sent to Google whatever scopes the MCP client asks for, so Tasks and Gmail are always offered.
        # GoogleProvider keeps its access_type=offline and prompt=consent defaults alongside.
        extra_authorize_params={"scope": " ".join(REQUESTED_SCOPES)},
        client_storage=store,
        jwt_signing_key=settings.server_key,
        # Every MCP request re-checks the Google token; caching keeps that to one call per 5 minutes
        cache_ttl_seconds=300,
    )
