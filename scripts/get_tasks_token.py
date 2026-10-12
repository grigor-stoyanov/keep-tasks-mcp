"""One-time: sign in with Google in your browser and print a Tasks refresh token.

Usage: pip install google-auth-oauthlib
       python scripts/get_tasks_token.py path/to/client_secret.json
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, ["https://www.googleapis.com/auth/tasks"])
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
client = json.load(open(path))["installed"]
print("\nGOOGLE_CLIENT_ID=" + client["client_id"])
print("GOOGLE_CLIENT_SECRET=" + client["client_secret"])
print("GOOGLE_REFRESH_TOKEN=" + creds.refresh_token)
