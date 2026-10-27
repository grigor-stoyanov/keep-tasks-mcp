# Delegated scopes for mail, calendar and Microsoft To Do. Mail.Send is only used by
# outlook_send_draft, which previews first (utils/send_guard.py); nothing can permanently delete.
# offline_access (for the refresh token) is added by MSAL automatically.
# Changing these means signing in again: `make env-outlook`, or outlook_connect on the shared server.
OUTLOOK_SCOPES = ["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite", "Tasks.ReadWrite", "User.Read"]
# Personal Microsoft accounts (outlook.com, hotmail.com, live.com)
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/consumers"

# Graph limits
MESSAGE_PAGE_SIZE = 250  # $top for listing messages
GRAPH_BATCH = 20  # requests per JSON $batch call
# Folders Graph accepts by name in place of an id
WELL_KNOWN_FOLDERS = frozenset({"inbox", "archive", "deleteditems", "junkemail", "drafts", "sentitems"})
