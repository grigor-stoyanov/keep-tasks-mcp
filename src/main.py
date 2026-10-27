import os

from server import google_mcp
import tools.gmail_tools  # noqa: F401
import tools.keep_tools  # noqa: F401
import tools.outlook_tools  # noqa: F401
import tools.task_tools  # noqa: F401

if __name__ == "__main__":
    # TODO: add gui for setting env vars
    secret = os.environ.get("MCP_SECRET")
    if not secret or len(secret) < 24:
        raise SystemExit("Set MCP_SECRET env var to a random string of at least 24 characters")
    google_mcp.run(
        transport=os.environ.get("MCP_TRANSPORT", "http"),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path=f"/{secret}/mcp",
        stateless_http=True,
    )