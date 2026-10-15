"""The FastMCP instance for the Google Tasks, Google Keep and Gmail tools.

This module only creates the server object. Tool modules import `google_mcp` from here and
register themselves with @google_mcp.tool; main.py imports them and runs the server.
"""

from fastmcp import FastMCP

google_mcp = FastMCP(
    "google-keep-tasks",
    instructions=(
        "Tools for the user's Google Tasks, Google Keep and Gmail. "
        "Call tasks_list_tasklists first to get tasklist ids; '@default' is the user's default list. "
        "For Gmail cleanup, use gmail_top_senders to find bulk senders, then gmail_bulk_trash with a "
        "search query: dry_run first, and only trash after the user confirms."
    ),
)
