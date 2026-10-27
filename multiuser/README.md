# Shared server for friends (experimental)

The same tools as `src/`, deployed as a second Cloud Run service that a few friends add to their AI
app with one URL and a Google sign-in. No secrets to copy, no Cloud project of their own, and it
stays inside Google Cloud's free tier.

The personal server in `src/` is untouched and keeps running as before.

## How it works

```
AI app --(OAuth)--> AllowlistGoogleProvider (auth.py) --> AccessPolicy (access.py) --> src/ tools
                                                                                          |
                                               per-caller clients (per_user.py) <---------+
```

- **Sign-in.** FastMCP's `GoogleProvider` runs the OAuth flow the AI app starts when the connector
  is added. `auth.py` checks the email Google returns against the allowlist *before* FastMCP stores
  anything; a stranger's tokens are revoked on the spot and they see "ask the owner to add you".
- **Optional services.** Google's consent screen offers Tasks, Gmail and Calendar, and people can
  untick any of them. Only `openid` and `email` are required; each tool checks that its own scope was granted,
  and tools of ungranted services are hidden.
- **Outlook is opt-in.** Sign-in is Google only, so a user who wants Outlook asks their AI app to
  "connect my Outlook". `outlook_connect` returns a microsoft.com link and code; once they've signed
  in, `outlook_connect_finish` stores their Microsoft refresh token. Until then they only see those
  two tools, so people without Outlook aren't shown 30 tools they can't use. People who linked
  Outlook while it was read-only are asked to link it again, to grant drafts, sending and To Do.
- **Reusing src/ unchanged.** The src/ tools call module-level client singletons. `per_user.install()`
  swaps them for subclasses that use the caller's token, before the tool modules are imported.
  `main.py` then attaches sign-in and the access policy to the existing `google_mcp` server.
- **Storage.** Everyone's Google and Microsoft tokens and the usage counters live in Firestore,
  encrypted with a key derived from `SERVER_KEY`.
- **Expired sign-ins** tell the user to reconnect the connector, or to contact the owner by email.

## Limits (so friends never cost you money)

| Guard | Where | Default |
|---|---|---|
| Allowlist, checked at sign-in and on every call | `friends_add` / `friends_remove` (seeded once from `FRIEND_EMAILS`) | empty |
| Hard cap on friends, a code change to raise | `MAX_FRIENDS` in `settings.py` | 10 |
| Successful tool calls (not messages) per friend per day; owner unlimited | `FRIEND_DAILY_CALLS` | 300 |
| Which services friends get | `FRIEND_SERVICES` | tasks, gmail, calendar, outlook |
| Owner-only services, can't be shared | `OWNER_ONLY_SERVICES` in `settings.py` | keep |
| Kill switch for all friends | `FRIENDS_ENABLED=false` | on |
| One instance at most, scales to zero when idle | `make deploy-friends` | `--max-instances 1` |

Only calls that succeed count towards the daily limit; refused, invalid and failing calls don't.

Rough free-tier math: a tool call costs a friend about 3 Firestore reads and 1 write. Firestore's
free tier is 50k reads and 20k writes per day, so 10 friends at 300 calls each is ~9k reads and
3k writes, under a fifth of it. Cloud Run's free tier (2M requests, 180k vCPU-seconds a month) is
further away still.

Google Cloud can't hard-stop spending; set a budget alert so you hear about it early:

```
gcloud billing budgets create --billing-account=<BILLING_ACCOUNT_ID> --display-name=keep-tasks \
  --budget-amount=1EUR --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

## Setup

1. **Firestore:** `make friends-setup` (once per project).
2. **Google OAuth client:** in the Cloud console create an OAuth client of type *Web application*
   with redirect URI `<PUBLIC_URL>/auth/callback`. On the consent screen add `openid`,
   `userinfo.email`, Tasks, Gmail and Calendar (`calendar.events`, `calendar.readonly`), enable the
   Google Calendar API, and keep the app *In production* (unverified). Google then
   shows friends an "unverified app" warning, and caps the app at 100 users ever.
3. **Azure app:** reuse the one from `make env-outlook`; it already accepts any personal account.
4. **Config:** copy `env.example.yaml` to `multiuser/env.yaml` (git-ignored) and fill it in.
5. **Deploy:** `make deploy-friends`.
6. **Invite:** connect to the server yourself and ask *"Add alex@gmail.com as a friend"*. The
   reply includes the invite to send them. See [Managing friends](#managing-friends).

## Managing friends

The allowlist lives in Firestore, so you change it from any chat with the connector, no redeploy.
These tools are only shown to, and only work for, `OWNER_EMAIL`:

| Tool | What it does |
|---|---|
| `friends_list` | Everyone on the list, when they were added, whether Outlook is linked, tool calls today |
| `friends_add(email, name)` | Adds them (up to `MAX_FRIENDS`) and returns a ready-to-send invite |
| `friends_remove(email)` | Cuts them off at once and deletes their linked Outlook token |

Try *"Who's using my connector today?"* or *"Remove alex@gmail.com"*.

`FRIEND_EMAILS` only seeds the list the first time the server starts; editing it later does
nothing. A removed friend's Google sign-in stays in the store but is refused on every request.
`FRIENDS_ENABLED=false` still cuts everyone off at once.

## Inviting friends

`friends_add` returns the invite. `make share-friends` prints the same text from the terminal,
to paste into a chat or email. It lists what they get,
links to `<PUBLIC_URL>/join`, and suggests a first message. `ARGS="--preview"` also opens the page
locally.

For Claude users the invite leads with **`<PUBLIC_URL>/add-to-claude`**, a one-click link. It
redirects to Claude's [install link](https://claude.com/docs/connectors/building/directory-vs-custom#share-an-install-link),
which opens *Add custom connector* with the name and URL already filled in; the friend only clicks
Add, then Connect. The /join page has the same **Add to Claude** button, and an **Ask it in Claude**
button that opens a new chat with the first question typed in. Custom connectors work on Claude's
Free plan too (one per account).

ChatGPT and Gemini have no link that fills in a connector, so the page does the next best thing:

- **Add to ChatGPT** copies the connector URL and opens `chatgpt.com/#settings/Connectors`; the
  friend pastes it into *Create*. ChatGPT moves its settings around often, so the steps underneath
  also say where to look. **Ask it in ChatGPT** opens a chat with the first question typed in.
- **Copy Gemini CLI command** copies `gemini mcp add keep-tasks <url> --transport http --scope user`;
  after running it they type `/mcp auth keep-tasks` in gemini to sign in.

The **/join page** is public and served by the server itself: the connector URL with a copy
button, the features this server shares, step-by-step setup for Claude, ChatGPT, Claude Code and
Gemini CLI, and the first thing to ask.

Once connected, the AI explains the connector by itself. The server instructions ask it to call
**`account_overview`** on first use, which returns the user's features with example requests, what
they could still enable (an unticked Google service, Outlook not linked yet), and their usage today.
The same tour is available as the **`getting_started`** prompt (in Claude: the + menu). The text
comes from one feature catalogue in `invite.py`, so the page, the invite and the AI always agree.

## Which AI apps can connect

The server speaks standard remote MCP with OAuth and Dynamic Client Registration, so in principle
any client that supports that works. In practice (October 2026):

| App | Status | Notes |
|---|---|---|
| **Claude** (web, desktop, mobile) | Works | *Settings -> Connectors -> Add custom connector*, paste the URL, sign in. The target client. |
| **ChatGPT** Business, Enterprise, Edu | Should work, untested | Custom connectors via *Developer mode*, with OAuth and write actions. |
| **ChatGPT** Plus, Pro | Possibly read-only, untested | OpenAI's docs disagree on whether these plans get custom connectors, or only read/fetch. Every tool is labelled read or write, so a read-only mode can still use the 24 read tools. |
| **ChatGPT** Free | No | Free accounts can't add custom connectors at all. That's OpenAI's limit; nothing on the server side changes it. |
| **Gemini app** (personal) | No | No way to add a custom MCP server to the consumer Gemini app. |
| **Gemini CLI** | Works, free | Remote MCP with OAuth in `~/.gemini/settings.json`, then `/mcp auth keep-tasks`. Free with a personal Google account; there are unconfirmed reports that Google is moving personal users to a successor CLI. |
| **Gemini Enterprise** | Not practical | Admin-only "Custom MCP Server" data store, in preview, no Dynamic Client Registration: it would need its own OAuth client and a Google-hosted redirect URI. |

**Read vs write.** Every tool carries MCP `readOnlyHint`/`destructiveHint` annotations
(`src/constants/tool_annotations.py`): 24 read, the rest write, with deletes, trashing,
overwrites and anything that emails people marked destructive. Sending also needs a preview and
a second call with `confirm=true`, enforced by the server (`src/utils/send_guard.py`). ChatGPT uses them to ask before writes, and read-only modes to pick
which tools to offer.

## Open questions for later

- **Untested end to end.** Needs a real OAuth client and Firestore; so far the wiring, allowlist,
  optional scopes and limits are checked locally with `STORE=memory` and faked tokens.
- **Pending Outlook sign-ins live in memory.** Fine with one instance; a restart mid-sign-in just
  means asking again.
