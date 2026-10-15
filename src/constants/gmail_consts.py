# gmail.modify can search, read headers and move mail to/from Trash. It deliberately cannot
# permanently delete (that needs the full https://mail.google.com/ scope), so every bulk action
# stays reversible for 30 days.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Gmail API hard limits
LIST_PAGE_SIZE = 500  # messages.list maxResults
MODIFY_CHUNK = 1000  # ids per messages.batchModify
# Google allows 100 calls per batch, but recommends <=50 for Gmail to avoid rateLimitExceeded
METADATA_BATCH = 50
