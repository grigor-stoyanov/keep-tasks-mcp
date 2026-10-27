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
- **Optional services.** Google's consent screen offers Tasks and Gmail, and people can untick
  either. Only `openid` and `email` are required; each tool checks that its own scope was granted,
  and tools of ungranted services are hidden.
- **Outlook is opt-in.** Sign-in is Google only, so a user who wants Outlook asks their AI app to
  "connect my Outlook". `outlook_connect` returns a microsoft.com link and code; once they've signed
  in, `outlook_connect_finish` stores their Microsoft refresh token. Until then they only see those
  two tools, so people without Outlook aren't shown 10 tools they can't use.
- **Reusing src/ unchanged.** The src/ tools call module-level client singletons. `per_user.install()`
  swaps them for subclasses that use the caller's token, before the tool modules are imported.
  `main.py` then attaches sign-in and the access policy to the existing `google_mcp` server.
- **Storage.** Everyone's Google and Microsoft tokens and the usage counters live in Firestore,
  encrypted with a key derived from `SERVER_KEY`.
- **Expired sign-ins** tell the user to reconnect the connector, or to contact the owner by email.

## Limits (so friends never cost you money)

| Guard | Where | Default |
|---|---|---|
| Allowlist, checked at sign-in and on every call | `FRIEND_EMAILS` | empty |
| Hard cap on friends, a code change to raise | `MAX_FRIENDS` in `settings.py` | 10 |
| Successful tool calls (not messages) per friend per day; owner unlimited | `FRIEND_DAILY_CALLS` | 300 |
| Which services friends get | `FRIEND_SERVICES` | tasks, gmail, outlook |
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
   `userinfo.email`, Tasks and Gmail, and keep the app *In production* (unverified). Google then
   shows friends an "unverified app" warning, and caps the app at 100 users ever.
3. **Azure app:** reuse the one from `make env-outlook`; it already accepts any personal account.
4. **Config:** copy `env.example.yaml` to `multiuser/env.yaml` (git-ignored) and fill it in.
5. **Deploy:** `make deploy-friends`. Friends add `<PUBLIC_URL>/mcp` as a custom connector and sign
   in with Google.

## Which AI apps can connect

The server speaks standard remote MCP with OAuth and Dynamic Client Registration, so in principle
any client that supports that works. In practice (October 2026):

| App | Status | Notes |
|---|---|---|
| **Claude** (web, desktop, mobile) | Works | *Settings -> Connectors -> Add custom connector*, paste the URL, sign in. The target client. |
| **ChatGPT** | Likely works, plan-dependent | Custom MCP connectors with OAuth live behind *Developer mode*. OpenAI's help center lists full MCP support (including write actions such as `gmail_bulk_trash` or `tasks_create_task`) for Business, Enterprise and Edu; for Plus and Pro its docs disagree on whether that's read-only or unavailable. Untested here. |
| **Gemini app** (consumer) | No | No confirmed way to add a custom MCP server to the personal Gemini app. |
| **Gemini Enterprise** | Not practical | Admin-only "Custom MCP Server" data store, in preview, no Dynamic Client Registration: it would need its own OAuth client and a Google-hosted redirect URI. |
| **Gemini CLI** | Works for technical friends | Remote MCP servers with OAuth are configured in `~/.gemini/settings.json`; it discovers the OAuth endpoints from the 401 response. |

If ChatGPT becomes a target: its connectors separate read from write actions, and the src/ tools
don't yet mark which they are. Adding `readOnlyHint` annotations (as the Outlook tools already have)
would let read-only plans use the read tools. The sign-in flow itself needs no change.

## Open questions for later

- **Untested end to end.** Needs a real OAuth client and Firestore; so far the wiring, allowlist,
  optional scopes and limits are checked locally with `STORE=memory` and faked tokens.
- **Pending Outlook sign-ins live in memory.** Fine with one instance; a restart mid-sign-in just
  means asking again.
