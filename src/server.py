"""The FastMCP instance for the Google Tasks and Google Keep tools.

This module only creates the server object. Tool modules import `google_mcp` from here and
register themselves with @google_mcp.tool; main.py imports them and runs the server.
"""

from fastmcp import FastMCP

google_mcp = FastMCP(
    "google-keep-tasks",
    instructions=(
        "Tools for the user's Google Tasks and Google Keep. "
        "Call tasks_list_tasklists first to get tasklist ids; '@default' is the user's default list."
    ),
)
