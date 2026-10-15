from email.utils import parseaddr


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
