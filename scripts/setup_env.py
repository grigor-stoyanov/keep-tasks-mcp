"""Create and manage env.yaml (the secrets for the MCP server). Driven by the Makefile.

Subcommands:
  login  Sign in to Google in the browser, generate MCP_SECRET, write env.yaml (Google Tasks + Gmail)
  keep     Add a Google Keep master token to env.yaml (optional, unofficial)
  outlook  Sign in to a personal Microsoft account, add an Outlook refresh token to env.yaml (optional)
  run      Load env.yaml and start the server locally
  url    Print the connector URL of the deployed Cloud Run service

Needs client_secret.json in the repo root: Google Cloud console -> APIs & Services -> Credentials
-> Create credentials -> OAuth client ID -> Desktop app -> download JSON.
"""
import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "env.yaml"
CLIENT_FILE = ROOT / "client_secret.json"
# One refresh token for both services; each client requests only its own scope from it
SCOPES = ["https://www.googleapis.com/auth/tasks", "https://www.googleapis.com/auth/gmail.modify"]
# Must match src/constants/outlook_consts.py
OUTLOOK_SCOPES = ["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite", "Tasks.ReadWrite", "User.Read"]
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/consumers"


def load_env() -> dict:
    """env.yaml holds one `KEY: "value"` per line; values are JSON strings, which are valid YAML."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith("#"):
                key, value = line.split(":", 1)
                env[key.strip()] = json.loads(value.strip())
    return env


def save_env(env: dict) -> None:
    ENV_FILE.write_text("".join(f"{k}: {json.dumps(v)}\n" for k, v in env.items()), encoding="utf-8")


def login(args) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_FILE.exists():
        sys.exit(f"Missing {CLIENT_FILE.name}. See the top of scripts/setup_env.py for how to get it.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    client = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))["installed"]

    env = load_env()
    env.setdefault("MCP_SECRET", secrets.token_urlsafe(32))  # keep the URL stable across re-logins
    env["GOOGLE_CLIENT_ID"] = client["client_id"]
    env["GOOGLE_CLIENT_SECRET"] = client["client_secret"]
    env["GOOGLE_REFRESH_TOKEN"] = creds.refresh_token
    save_env(env)
    print(f"Wrote {ENV_FILE.name} (Google Tasks and Gmail ready).")


def keep(args) -> None:
    import gpsoauth

    print("1. Open https://accounts.google.com/EmbeddedSetup in a private window and sign in.")
    print("2. DevTools -> Application -> Cookies -> accounts.google.com -> copy the `oauth_token` value.")
    print("   It is single use and expires within minutes, so paste it right away.\n")
    email = input("Google email: ").strip()
    oauth_token = getpass.getpass("oauth_token cookie (hidden): ").strip()
    resp = gpsoauth.exchange_token(email, oauth_token, uuid.uuid4().hex[:16])
    if "Token" not in resp:
        sys.exit(f"Failed: {resp}")
    env = load_env()
    env["KEEP_EMAIL"] = email
    env["KEEP_MASTER_TOKEN"] = resp["Token"]
    save_env(env)
    print(f"Wrote Keep credentials to {ENV_FILE.name}.")


def outlook(args) -> None:
    import msal

    env = load_env()
    client_id = env.get("OUTLOOK_CLIENT_ID") or input("Azure app registration's Application (client) ID: ").strip()
    app = msal.PublicClientApplication(client_id, authority=OUTLOOK_AUTHORITY)
    flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPES)
    if "user_code" not in flow:
        sys.exit(f"Failed to start sign-in: {flow.get('error_description', flow)}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "refresh_token" not in result:
        sys.exit(f"Sign-in failed: {result.get('error_description', result)}")
    env["OUTLOOK_CLIENT_ID"] = client_id
    env["OUTLOOK_REFRESH_TOKEN"] = result["refresh_token"]
    save_env(env)
    print(f"Wrote Outlook credentials to {ENV_FILE.name}.")


def run(args) -> None:
    env = load_env()
    if "MCP_SECRET" not in env:
        sys.exit("No env.yaml yet. Run: make env")
    port = os.environ.get("PORT", "8080")
    print(f"Local URL: http://localhost:{port}/{env['MCP_SECRET']}/mcp")
    print(f"Add to Claude Code: claude mcp add --transport http keep-tasks http://localhost:{port}/{env['MCP_SECRET']}/mcp\n")
    subprocess.run([sys.executable, "main.py"], cwd=ROOT / "src", env={**os.environ, **env})


def url(args) -> None:
    gcloud = shutil.which("gcloud")
    if not gcloud:
        sys.exit("gcloud not found. Run: make gcloud-install")
    cmd = [gcloud, "run", "services", "describe", args.service, "--region", args.region, "--format", "value(status.url)"]
    if args.project:
        cmd += ["--project", args.project]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(result.stderr.strip() or "Could not describe the service. Did you run: make deploy")
    secret = load_env().get("MCP_SECRET", "<MCP_SECRET>")
    connector = f"{result.stdout.strip()}/{secret}/mcp"
    print(f"Connector URL: {connector}")
    print(f"Claude Code:   claude mcp add --transport http keep-tasks {connector}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login").set_defaults(func=login)
    sub.add_parser("keep").set_defaults(func=keep)
    sub.add_parser("outlook").set_defaults(func=outlook)
    sub.add_parser("run").set_defaults(func=run)
    p = sub.add_parser("url")
    p.add_argument("--service", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--project", default="")
    p.set_defaults(func=url)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
