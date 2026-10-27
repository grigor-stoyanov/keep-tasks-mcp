# Read-only delegated scopes: the token itself cannot send, move or delete mail or events, so the
# read-only guarantee is enforced by Microsoft, not only by which tools are registered.
# offline_access (for the refresh token) is added by MSAL automatically.
OUTLOOK_SCOPES = ["Mail.Read", "Calendars.Read", "User.Read"]
# Personal Microsoft accounts (outlook.com, hotmail.com, live.com)
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/consumers"
