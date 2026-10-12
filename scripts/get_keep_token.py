"""One-time: exchange a Google 'oauth_token' cookie for a Keep master token (unofficial).

1. In a private browser window open https://accounts.google.com/EmbeddedSetup and sign in.
   (The page may spin or show an error at the end - that's fine.)
2. DevTools -> Application -> Cookies -> accounts.google.com -> copy the value of `oauth_token`
   (starts with "oauth2_4/").
3. pip install gpsoauth && python scripts/get_keep_token.py you@gmail.com

The cookie is single-use and expires within minutes, so run this right after copying it.
"""
import getpass
import sys
import uuid

import gpsoauth

email = sys.argv[1] if len(sys.argv) > 1 else input("Google email: ")
oauth_token = getpass.getpass("oauth_token cookie (hidden): ").strip()
resp = gpsoauth.exchange_token(email, oauth_token, uuid.uuid4().hex[:16])
if "Token" not in resp:
    sys.exit(f"Failed: {resp}")
print("\nKEEP_EMAIL=" + email)
print("KEEP_MASTER_TOKEN=" + resp["Token"])
