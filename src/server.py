"""The FastMCP instance for the Google Tasks, Keep, Gmail and Calendar tools, and the Outlook ones.

This module only creates the server object. Tool modules import `google_mcp` from here and
register themselves with @google_mcp.tool; main.py imports them and runs the server.
"""

from fastmcp import FastMCP

google_mcp = FastMCP(
    "google-keep-tasks",
    instructions=(
        "Tools for the user's Google Tasks, Google Keep, Gmail and Google Calendar, and their Outlook.com "
        "mail, calendar and Microsoft To Do. "
        "Call tasks_list_tasklists first to get tasklist ids; '@default' is the user's default list. "
        "Sending email: write a draft (gmail_create_draft, outlook_create_draft or "
        "outlook_create_reply_draft), then call the send tool without confirm, show the user the "
        "preview it returns, and only call again with confirm=true after the user explicitly agrees. "
        "Invitations and changes to events with guests work the same way. Never confirm on the "
        "user's behalf. "
        "For bulk cleanup, find senders first (gmail_top_senders, outlook_top_senders), then use "
        "gmail_bulk_trash or outlook_bulk_move: dry_run first, and only after the user confirms call "
        "again with dry_run=false and the confirm_token the dry run returned."
    ),
)
