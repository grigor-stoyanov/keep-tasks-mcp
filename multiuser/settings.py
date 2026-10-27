"""Settings and hard limits for the shared server, read once at startup."""
import os
from dataclasses import dataclass

# Hard ceiling on friends, on top of the allowlist (friends.py). Raising it is meant to be a
# deliberate code change: Google caps an unverified app at 100 users for its lifetime, and every
# friend adds Cloud Run and Firestore usage that is billed to you once past the free tier.
MAX_FRIENDS = 10
# Tool names start with their service, e.g. gmail_bulk_trash -> "gmail"
SERVICES = frozenset({"tasks", "gmail", "outlook", "keep", "friends"})
# Keep signs in with the owner's master token, so it can never be shared; friends_* manage the allowlist
OWNER_ONLY_SERVICES = frozenset({"keep", "friends"})


@dataclass(frozen=True)
class Settings:
    public_url: str
    server_key: str
    oauth_client_id: str
    oauth_client_secret: str
    owner_email: str
    friend_emails: frozenset[str]
    friend_services: frozenset[str]
    friend_daily_calls: int
    friends_enabled: bool
    outlook_client_id: str
    store: str


def _csv(raw: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Set the {name} env var (see multiuser/env.example.yaml)")
    return value


def load_settings() -> Settings:
    server_key = _require("SERVER_KEY")
    if len(server_key) < 32:
        raise SystemExit("SERVER_KEY must be a random string of at least 32 characters")

    friends = _csv(os.environ.get("FRIEND_EMAILS", ""))
    if len(friends) > MAX_FRIENDS:
        raise SystemExit(f"FRIEND_EMAILS lists {len(friends)} people; the limit is MAX_FRIENDS={MAX_FRIENDS}")

    friend_services = _csv(os.environ.get("FRIEND_SERVICES", "tasks,gmail,outlook"))
    if unknown := friend_services - SERVICES:
        raise SystemExit(f"Unknown FRIEND_SERVICES: {', '.join(sorted(unknown))}")
    if shared := friend_services & OWNER_ONLY_SERVICES:
        raise SystemExit(f"These services can't be shared with friends: {', '.join(sorted(shared))}")

    return Settings(
        public_url=_require("PUBLIC_URL").rstrip("/"),
        server_key=server_key,
        oauth_client_id=_require("OAUTH_CLIENT_ID"),
        oauth_client_secret=_require("OAUTH_CLIENT_SECRET"),
        owner_email=_require("OWNER_EMAIL").lower(),
        friend_emails=friends,
        friend_services=friend_services,
        friend_daily_calls=int(os.environ.get("FRIEND_DAILY_CALLS", "300")),
        friends_enabled=os.environ.get("FRIENDS_ENABLED", "true").strip().lower() == "true",
        outlook_client_id=os.environ.get("OUTLOOK_CLIENT_ID", "").strip(),
        store=os.environ.get("STORE", "firestore").strip().lower(),
    )
