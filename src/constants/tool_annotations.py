from mcp.types import ToolAnnotations

# MCP clients use these to tell read tools from write tools: ChatGPT asks before running a write,
# and plans limited to read-only connectors only get the READ tools.
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
# Overwrites, deletes or trashes something the user already has
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)
# Emails other people (sending mail, invitations, replies to invites). It can't be undone, so it's
# marked destructive for AI apps to ask first; the tools also need a preview first (utils/send_guard.py).
SEND = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)
