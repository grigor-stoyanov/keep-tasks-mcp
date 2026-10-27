import base64
import html
import re
from email.utils import parseaddr

_HIDDEN_HTML = re.compile(r"<(script|style|head)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_TAGS = re.compile(r"<\s*(br|/p|/div|/tr|/li|/h\d)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n\s*\n\s*\n+")


def _header(msg: dict, name: str) -> str | None:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return None


def _message_view(msg: dict) -> dict:
    return {"id": msg["id"], "from": _header(msg, "From"), "subject": _header(msg, "Subject"), "date": _header(msg, "Date")}


def _sender(msg: dict) -> tuple[str, str]:
    """(display name, lowercased email address) of the From header."""
    name, addr = parseaddr(_header(msg, "From") or "")
    return name, addr.lower()


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(markup: str) -> str:
    text = _TAGS.sub("", _BLOCK_TAGS.sub("\n", _HIDDEN_HTML.sub("", markup)))
    return _BLANK_LINES.sub("\n\n", html.unescape(text)).strip()


def _body_text(payload: dict) -> str:
    """The readable text of a message: its text/plain parts, or its HTML with the markup removed."""
    plain, rich = [], []

    def walk(part: dict) -> None:
        data = part.get("body", {}).get("data")
        if data and not part.get("filename"):
            if part.get("mimeType") == "text/plain":
                plain.append(_decode(data))
            elif part.get("mimeType") == "text/html":
                rich.append(_decode(data))
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return "\n".join(plain).strip() if plain else _html_to_text("\n".join(rich))


def _attachments(payload: dict) -> list[str]:
    names = []

    def walk(part: dict) -> None:
        if part.get("filename"):
            names.append(part["filename"])
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return names
