"""Entrypoint for the shared server: the src/ tools behind Google sign-in, for the owner and a few friends.

The order matters: per_user.install() swaps the src/ client singletons before the tool modules
import them, then sign-in and the access policy are attached to the existing src/ server object.
"""
import os
import sys
from pathlib import Path

# After this folder, so a module here is never shadowed by one in src/
sys.path.insert(1, str(Path(__file__).resolve().parent.parent / "src"))

import per_user  # noqa: E402
from access import AccessPolicy  # noqa: E402
from auth import build_auth, build_store  # noqa: E402
from friends import Friends  # noqa: E402
from settings import load_settings  # noqa: E402

settings = load_settings()
store = build_store(settings)
friends = Friends(store, settings)
outlook_accounts = per_user.install(store, settings)

import connect_tools  # noqa: E402
import friend_tools  # noqa: E402
import onboarding  # noqa: E402
import tools.calendar_tools  # noqa: E402, F401
import tools.gmail_mail_tools  # noqa: E402, F401
import tools.gmail_tools  # noqa: E402, F401
import tools.keep_tools  # noqa: E402, F401
import tools.outlook_mail_tools  # noqa: E402, F401
import tools.outlook_tools  # noqa: E402, F401
import tools.task_tools  # noqa: E402, F401
from server import google_mcp  # noqa: E402

connect_tools.register(outlook_accounts)
friend_tools.register(friends, outlook_accounts, settings, store)
onboarding.register(settings, store, friends)
google_mcp.auth = build_auth(settings, store, friends)
google_mcp.add_middleware(AccessPolicy(settings, store, friends))

if __name__ == "__main__":
    google_mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path="/mcp",
        stateless_http=True,
    )
