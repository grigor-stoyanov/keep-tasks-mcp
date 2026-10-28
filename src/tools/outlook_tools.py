"""Outlook.com mail and calendar, reused from the outlook-personal-mcp package.

outlook-personal-mcp (https://github.com/salahawad/outlook-personal-mcp, MIT) defines its tools
inside plain register(mcp, client) functions, so instead of forking it we call those functions
with a stand-in for the server that registers the tools listed in UPSTREAM_TOOLS on google_mcp,
under an `outlook_` prefix and with our own annotations. Everything else is dropped.
outlook_mail_tools.py adds what upstream doesn't do safely: sending, replies, event changes that
email attendees, and bulk moves.
"""
import os

from outlook_personal_mcp.config import Settings
from outlook_personal_mcp.tools import calendar, drafts, folders, mail

from clients.outlook_client import outlook_graph
from constants.tool_annotations import DESTRUCTIVE, READ, WRITE
from server import google_mcp

# Left out on purpose:
# - send_mail, reply, forward and send_draft send in one call; outlook_send_draft previews first
# - create_event, update_event, delete_event and respond_event email attendees or the organizer
#   straight away; the versions in outlook_mail_tools.py preview first
# - add_attachment and download_attachment read and write the server's own disk
# - copy_message, rename_folder, delete_folder and permanent_delete
UPSTREAM_TOOLS = {
    "list_folders": READ,
    "list_messages": READ,
    "search_messages": READ,
    "get_message": READ,
    "list_attachments": READ,
    "list_calendars": READ,
    "list_events": READ,
    "search_events": READ,
    "get_event": READ,
    "find_availability": READ,
    "create_draft": WRITE,
    "update_draft": WRITE,
    "create_folder": WRITE,
    "move_message": WRITE,
    "mark_read": WRITE,
    "flag_message": WRITE,
    "delete_message": DESTRUCTIVE,  # to Deleted Items, recoverable
}


class _Registrar:
    """Passed to the upstream register() functions in place of their FastMCP server."""

    def tool(self, annotations=None):
        def register(fn):
            if fn.__name__ in UPSTREAM_TOOLS:
                google_mcp.tool(fn, name=f"outlook_{fn.__name__}", annotations=UPSTREAM_TOOLS[fn.__name__])
            return fn
        return register


_registrar = _Registrar()
# Upstream reads settings at registration time, only to decide whether to add permanent_delete (off by default)
_settings = Settings(client_id=os.environ.get("OUTLOOK_CLIENT_ID", ""))
folders.register(_registrar, outlook_graph)
mail.register(_registrar, outlook_graph, _settings)
drafts.register(_registrar, outlook_graph, _settings)
calendar.register(_registrar, outlook_graph)
