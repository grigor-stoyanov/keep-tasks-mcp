import html
import re

_HIDDEN_HTML = re.compile(r"<(script|style|head)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_TAGS = re.compile(r"<\s*(br|/p|/div|/tr|/li|/h\d)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n\s*\n\s*\n+")


def html_to_text(markup: str) -> str:
    """Readable text from an email's HTML: no scripts, styles or tags, one line break per block."""
    text = _TAGS.sub("", _BLOCK_TAGS.sub("\n", _HIDDEN_HTML.sub("", markup)))
    return _BLANK_LINES.sub("\n\n", html.unescape(text)).strip()
