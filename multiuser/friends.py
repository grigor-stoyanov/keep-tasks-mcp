"""The friends allowlist, kept in the store so the owner can change it from a chat, no redeploy.

FRIEND_EMAILS only seeds it the first time the server starts with an empty store. After that the
owner's friends_add and friends_remove tools (friend_tools.py) are the way to change it.
"""
import re
import time
from datetime import datetime, timezone

from fastmcp.exceptions import ToolError
from key_value.aio.protocols.key_value import AsyncKeyValue

from settings import MAX_FRIENDS, Settings

COLLECTION, KEY = "friends", "allowlist"
# The allowlist is checked on every request. All writes go through the one instance and update the
# cache at once, so this only matters if two instances overlap briefly during a redeploy.
CACHE_SECONDS = 60
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}")


class Friends:
    def __init__(self, store: AsyncKeyValue, settings: Settings):
        self._store = store
        self._settings = settings
        self._cache: dict[str, dict] | None = None
        self._loaded_at = 0.0

    async def all(self) -> dict[str, dict]:
        """email -> {"added": date}"""
        if self._cache is None or time.monotonic() - self._loaded_at > CACHE_SECONDS:
            await self._load()
        return self._cache

    async def contains(self, email: str) -> bool:
        return bool(email) and email in await self.all()

    async def add(self, email: str) -> bool:
        """True if added, False if they were already on the list."""
        email = email.strip().lower()
        if not _EMAIL.fullmatch(email):
            raise ToolError(f"{email!r} doesn't look like an email address")
        if email == self._settings.owner_email:
            raise ToolError("That's the owner's own address; the owner always has access")
        friends = await self._load()
        if email in friends:
            return False
        if len(friends) >= MAX_FRIENDS:
            raise ToolError(f"Already {len(friends)} friends, the limit (MAX_FRIENDS in settings.py). Remove someone first.")
        friends[email] = {"added": datetime.now(timezone.utc).date().isoformat()}
        await self._save(friends)
        return True

    async def remove(self, email: str) -> bool:
        """True if removed, False if they weren't on the list."""
        email = email.strip().lower()
        friends = await self._load()
        if friends.pop(email, None) is None:
            return False
        await self._save(friends)
        return True

    async def _load(self) -> dict[str, dict]:
        # Writes always start from a fresh read, so a stale cache can't undo someone else's change
        stored = await self._store.get(KEY, collection=COLLECTION)
        if stored is None:
            seed = self._settings.friend_emails - {self._settings.owner_email}
            stored = {"emails": {email: {"added": "FRIEND_EMAILS"} for email in sorted(seed)}}
            await self._store.put(KEY, stored, collection=COLLECTION)
        self._cache, self._loaded_at = dict(stored["emails"]), time.monotonic()
        return dict(self._cache)

    async def _save(self, friends: dict[str, dict]) -> None:
        await self._store.put(KEY, {"emails": friends}, collection=COLLECTION)
        self._cache, self._loaded_at = dict(friends), time.monotonic()
