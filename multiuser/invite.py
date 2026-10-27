"""The feature catalogue, invite message and /join page for the shared server.

Pure functions with no server imports, so share.py can build the invite without starting anything.
"""
import html
import json
from urllib.parse import quote, urlencode

CONNECTOR_NAME = "keep-tasks"
FIRST_PROMPT = "What can my new keep-tasks connector do for me?"

FEATURES = {
    "tasks": {
        "title": "Google Tasks",
        "what": "See, add, update and complete your to-dos and task lists.",
        "try": ["What's due this week?", "Add 'book the dentist' to my tasks for Friday"],
    },
    "gmail": {
        "title": "Gmail cleanup",
        "what": "Find who floods your inbox and trash their mail in bulk. Always a dry run first, "
                "and everything stays recoverable from Trash for 30 days.",
        "try": ["Who sends me the most unread promotions?", "Trash everything from my top 5 senders"],
    },
    "outlook": {
        "title": "Outlook.com (read-only)",
        "what": "Search and read your Outlook mail and check your calendar. It can't send, move "
                "or delete anything. Link it once by asking to connect your Outlook.",
        "try": ["Connect my Outlook", "Summarise my unread Outlook emails", "What's on my calendar tomorrow?"],
    },
    "keep": {
        "title": "Google Keep",
        "what": "Search, create and edit notes and checklists.",
        "try": ["Make a packing checklist for a weekend trip"],
    },
}


def connector_url(public_url: str) -> str:
    return f"{public_url.rstrip('/')}/mcp"


def claude_install_link(public_url: str) -> str:
    """Opens claude.ai's Add custom connector dialog with the name and URL filled in; the user
    just confirms. https://claude.com/docs/connectors/building/directory-vs-custom#share-an-install-link"""
    query = urlencode({"modal": "add-custom-connector", "connectorName": CONNECTOR_NAME, "connectorUrl": connector_url(public_url)})
    return f"https://claude.ai/customize/connectors?{query}"


def add_to_claude_link(public_url: str) -> str:
    """A short link on this server that redirects to claude_install_link, easy to paste in a chat."""
    return f"{public_url.rstrip('/')}/add-to-claude"


def claude_first_chat_link() -> str:
    """A new Claude chat with the first question already typed in."""
    return f"https://claude.ai/new?q={quote(FIRST_PROMPT)}"


def setup_steps(public_url: str) -> list[dict]:
    """How to add the connector in each app, for the join page."""
    url = connector_url(public_url)
    gemini_config = json.dumps({"mcpServers": {CONNECTOR_NAME: {"httpUrl": url}}}, indent=2)
    return [
        {
            "app": "Claude (web, desktop, mobile)",
            "steps": [
                "Click Add to Claude above. Claude opens with the connector filled in: click Add, then Connect. "
                "(Or by hand: Customize, then Connectors, then Add custom connector, and paste the URL.)",
                "Sign in with your Google account. Google warns that the app is unverified: "
                "choose Advanced, then continue. Untick anything you don't want to share.",
            ],
        },
        {
            "app": "ChatGPT",
            "note": "Needs Developer mode, which OpenAI offers on paid plans only (fully on Business, "
                    "Enterprise and Edu; Plus and Pro may be limited to read-only tools). Not on Free.",
            "steps": [
                "Open Settings, then Apps (or Apps & Connectors), then Advanced settings, and turn on Developer mode.",
                "Create a new app or connector, paste the connector URL and choose OAuth.",
                "Sign in with your Google account when asked.",
            ],
        },
        {
            "app": "Claude Code",
            "code": f"claude mcp add --transport http {CONNECTOR_NAME} {url}",
            "steps": ["Run this in a terminal, then type /mcp in Claude Code to sign in."],
        },
        {
            "app": "Gemini CLI",
            "note": "The personal Gemini app can't add connectors; the free Gemini CLI can.",
            "code": gemini_config,
            "steps": ["Add this to ~/.gemini/settings.json, start gemini and run /mcp auth keep-tasks to sign in."],
        },
    ]


def invite_message(public_url: str, owner_email: str, services: frozenset[str], daily_calls: int, name: str = "") -> str:
    """Plain text to paste into a chat or email."""
    features = "\n".join(f"- {FEATURES[s]['title']}: {FEATURES[s]['what']}" for s in sorted(services))
    return (
        f"Hi{' ' + name if name else ''}! I've set you up on my AI assistant connector. Once it's added, "
        f"your AI app (Claude works best, ChatGPT on paid plans) can do this for you:\n\n"
        f"{features}\n\n"
        f"Using Claude? One click adds it: {add_to_claude_link(public_url)}\n"
        f"Other apps, and step-by-step help: {public_url.rstrip('/')}/join\n\n"
        f"Then ask it: \"{FIRST_PROMPT}\"\n\n"
        f"It signs in with your own Google account, and you can untick anything you don't want to "
        f"share. You get {daily_calls} actions a day. Questions: {owner_email}"
    )


def join_page(public_url: str, owner_email: str, services: frozenset[str]) -> str:
    esc = html.escape
    url = connector_url(public_url)
    features = "".join(
        f"<li><strong>{esc(FEATURES[s]['title'])}</strong> {esc(FEATURES[s]['what'])}"
        f"<span class=try>Try: {' · '.join(esc(t) for t in FEATURES[s]['try'])}</span></li>"
        for s in sorted(services)
    )
    apps = "".join(
        f"<details{' open' if i == 0 else ''}><summary>{esc(a['app'])}</summary>"
        + (f"<p class=note>{esc(a['note'])}</p>" if a.get("note") else "")
        + "<ol>" + "".join(f"<li>{esc(s)}</li>" for s in a["steps"]) + "</ol>"
        + (f"<div class=copy><pre>{esc(a['code'])}</pre><button data-copy=\"{esc(a['code'])}\">Copy</button></div>" if a.get("code") else "")
        + "</details>"
        for i, a in enumerate(setup_steps(public_url))
    )
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>Join Keep Tasks</title>
<style>
:root {{ --bg:#f7f7f5; --card:#fff; --text:#1d1d1b; --muted:#66655f; --line:#e3e2dc; --accent:#2f6fde; --on-accent:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --card:#21211f; --text:#ecebe6; --muted:#a3a29b; --line:#34332f; --accent:#7aa5f5; --on-accent:#10233f; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--text); font:16px/1.55 system-ui, -apple-system, Segoe UI, sans-serif }}
main {{ max-width:680px; margin:0 auto; padding:32px 16px 48px }}
h1 {{ font-size:1.6rem; margin:0 0 4px }} h2 {{ font-size:1.05rem; margin:28px 0 10px }}
.lead {{ color:var(--muted); margin:0 0 20px }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px }}
.copy {{ display:flex; gap:8px; align-items:flex-start }}
pre {{ flex:1; margin:0; padding:10px 12px; background:var(--bg); border:1px solid var(--line); border-radius:8px; overflow-x:auto; font-size:.85rem; white-space:pre-wrap; word-break:break-all }}
button {{ font:inherit; font-size:.85rem; padding:8px 12px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:var(--on-accent); cursor:pointer }}
ul.features {{ list-style:none; padding:0; margin:0; display:grid; gap:10px }}
ul.features li {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px }}
.try {{ display:block; color:var(--muted); font-size:.9rem; margin-top:4px }}
details {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:10px }}
summary {{ font-weight:600; cursor:pointer }} ol {{ padding-left:20px; margin:10px 0 }}
.note {{ color:var(--muted); font-size:.9rem; margin:10px 0 0 }}
.cta {{ display:inline-block; padding:12px 20px; border-radius:10px; background:var(--accent); color:var(--on-accent); font-weight:600; text-decoration:none }}
.cta.secondary {{ background:transparent; color:var(--accent); border:1px solid var(--accent); padding:9px 16px; font-weight:500 }}
.hint {{ color:var(--muted); font-size:.9rem; margin:0 0 8px }}
footer {{ color:var(--muted); font-size:.85rem; margin-top:28px }} a {{ color:var(--accent) }}
</style></head><body><main>
<h1>You're invited to Keep Tasks</h1>
<p class=lead>A connector that lets your AI assistant work with your own Google Tasks, Gmail and Outlook. Invite only.</p>
<p><a class=cta href="{esc(claude_install_link(public_url))}" target=_blank rel=noopener>Add to Claude</a></p>
<p class=hint>Opens Claude with everything filled in, you just click Add. Using another app? Copy the URL:</p>
<div class="card copy"><pre id=url>{esc(url)}</pre><button data-copy="{esc(url)}">Copy URL</button></div>
<h2>What you can do</h2><ul class=features>{features}</ul>
<h2>Add it to your AI app</h2>{apps}
<h2>Then ask</h2><div class="card copy"><pre>{esc(FIRST_PROMPT)}</pre><button data-copy="{esc(FIRST_PROMPT)}">Copy</button></div>
<p><a class="cta secondary" href="{esc(claude_first_chat_link())}" target=_blank rel=noopener>Ask it in Claude</a></p>
<footer>You sign in with your own Google account and only share what you tick. Run by {esc(owner_email)}.
<a href="https://github.com/grigor-stoyanov/keep-tasks-mcp/blob/master/PRIVACY.md#the-shared-server-if-a-friend-invited-you">Privacy</a> ·
<a href="https://github.com/grigor-stoyanov/keep-tasks-mcp/blob/master/TERMS.md#5-shared-servers">Terms</a></footer>
</main><script>
document.querySelectorAll("button[data-copy]").forEach(b => b.addEventListener("click", async () => {{
  try {{ await navigator.clipboard.writeText(b.dataset.copy); const t = b.textContent; b.textContent = "Copied"; setTimeout(() => b.textContent = t, 1500); }} catch (e) {{}}
}}));
</script></body></html>"""
