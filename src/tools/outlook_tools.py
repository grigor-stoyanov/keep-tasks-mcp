"""Read-only Outlook.com mail and calendar, reused from the outlook-personal-mcp package.

outlook-personal-mcp (https://github.com/salahawad/outlook-personal-mcp, MIT) defines its tools
inside plain register(mcp, client) functions, so instead of forking it we call those functions
with a stand-in for the server that registers each tool on google_mcp under an `outlook_` prefix.
Only tools it marks readOnlyHint=True get through; send, move, delete, drafts and attachment
downloads are dropped. The token's scopes are read-only as well (see constants/outlook_consts.py).
"""
import os

from outlook_personal_mcp.config import Settings
from outlook_personal_mcp.tools import calendar, folders, mail

from clients.outlook_client import outlook_graph
from server import google_mcp


class _ReadOnlyRegistrar:
    """Passed to the upstream register() functions in place of their FastMCP server."""

    def tool(self, annotations=None):
        def register(fn):
            if annotations is not None and annotations.read_only_hint:
                google_mcp.tool(fn, name=f"outlook_{fn.__name__}", annotations=annotations)
            return fn
        return register


_registrar = _ReadOnlyRegistrar()
folders.register(_registrar, outlook_graph)
# mail reads settings at registration time, only to decide whether to add permanent_delete (off by default)
mail.register(_registrar, outlook_graph, Settings(client_id=os.environ.get("OUTLOOK_CLIENT_ID", "")))
calendar.register(_registrar, outlook_graph)
