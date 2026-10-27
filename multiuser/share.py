"""Print an invite to paste into a chat or email, built from multiuser/env.yaml.

The invite links to the server's /join page, which shows each friend how to add the connector in
their AI app and what to ask first.

  make share-friends                      # the invite text
  make share-friends ARGS="--name Alex"   # with a greeting
  make share-friends ARGS="--preview"     # also write the /join page to a local file to look at
"""
import argparse
import json
import sys
import tempfile
import webbrowser
from pathlib import Path

from invite import invite_message, join_page

ENV_FILE = Path(__file__).resolve().parent / "env.yaml"


def load_env() -> dict:
    """env.yaml holds one `KEY: "value"` per line; values are JSON strings, which are valid YAML."""
    if not ENV_FILE.exists():
        sys.exit(f"No {ENV_FILE}. Copy env.example.yaml to it and fill it in first.")
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            env[key.strip()] = json.loads(value.strip())
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="", help="friend's name for the greeting")
    parser.add_argument("--preview", action="store_true", help="open the /join page locally")
    args = parser.parse_args()

    env = load_env()
    public_url, owner = env.get("PUBLIC_URL", ""), env.get("OWNER_EMAIL", "")
    if not public_url or "xxxxxxxxxx" in public_url or not owner:
        sys.exit("Set PUBLIC_URL and OWNER_EMAIL in multiuser/env.yaml first.")
    services = frozenset(s.strip() for s in env.get("FRIEND_SERVICES", "tasks,gmail,outlook").split(",") if s.strip())
    daily_calls = int(env.get("FRIEND_DAILY_CALLS", "300"))

    if not env.get("FRIEND_EMAILS"):
        print("Note: FRIEND_EMAILS is empty, so nobody can sign in yet.\n", file=sys.stderr)
    print(invite_message(public_url, owner, services, daily_calls, args.name))

    if args.preview:
        page = Path(tempfile.gettempdir()) / "keep-tasks-join.html"
        page.write_text(join_page(public_url, owner, services), encoding="utf-8")
        webbrowser.open(page.as_uri())
        print(f"\nPreview: {page}", file=sys.stderr)


if __name__ == "__main__":
    main()
