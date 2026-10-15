# Google Keep + Tasks MCP Server

A remote [Model Context Protocol](https://modelcontextprotocol.io) server that lets an AI assistant
read and manage my **Google Tasks** and **Google Keep** notes, and bulk-clean my **Gmail**. It runs over Streamable HTTP, so it
can be added to Claude as a custom connector and used from the desktop and mobile apps.

I built it to learn how MCP servers work end to end: tool design, auth, deployment, and keeping a
codebase small enough to extend without fear.

## What it does

17 tools, grouped by service:

| Service | Tools |
|---|---|
| **Google Tasks** (official API) | `tasks_list_tasklists`, `tasks_create_tasklist`, `tasks_list_tasks`, `tasks_create_task`, `tasks_update_task`, `tasks_delete_task`, `tasks_get_task_by_title` |
| **Google Keep** (unofficial, `gkeepapi`) | `keep_search_notes`, `keep_get_note`, `keep_create_note`, `keep_create_list`, `keep_update_note`, `keep_update_list`, `keep_trash_note` |
| **Gmail** (official API) | `gmail_top_senders`, `gmail_bulk_trash`, `gmail_restore_from_trash` |

Example prompts: *"What's due this week?"*, *"Add a checklist called Groceries with milk, eggs and bread"*,
*"Move everything labelled work to archived"*,
*"Who sends me the most unread promotions? Trash everything from the top five."*

## Architecture

```
src/
  main.py            entrypoint: imports the tool modules, then runs the server
  server.py          the FastMCP instance, nothing else
  tools/             MCP layer: parameters, validation, response shaping
    task_tools.py
    keep_tools.py
    gmail_tools.py
  clients/           one class per Google service: auth, locking, raw calls
    task_client.py
    keep_client.py
    gmail_client.py
  utils/             pure helpers (date parsing, paging, response views)
  constants/         OAuth scopes
```

Dependencies only point one way: `main -> tools -> clients`. Nothing in `clients/` knows about MCP
beyond raising `ToolError`.

### Design decisions

- **Thin clients, smart tools.** A client method makes exactly one call to Google with the
  parameters it is given and returns the raw response. Tools decide everything else: validation,
  paging through `nextPageToken`, and the shape of what the model sees. This keeps clients
  trivial to reason about and gives the tool layer one obvious place for behaviour.
- **Lazy, cached clients behind a lock.** Each client is a module-level singleton that builds its
  service on first use, so a missing Keep credential never stops the Tasks tools from working. The
  Google API objects are not thread-safe and FastMCP runs sync tools in a thread pool, so every
  call is serialised with a lock.
- **Tool contracts are explicit.** For example `tasks_update_task` requires every field and
  rejects `null` with a clear message, so the model can't silently wipe a task by omission.
- **Bulk actions take a query, not ids.** Off-the-shelf Gmail connectors make the model search,
  collect ids and delete them a page at a time, which falls over at thousands of messages. The
  Gmail tools take one Gmail search query and do the paging and 1000-id `batchModify` chunks
  server-side, so clearing 9,000 promotions is one tool call. They only ever move mail to Trash
  (the `gmail.modify` scope can't permanently delete), `gmail_bulk_trash` defaults to a dry run,
  and `gmail_restore_from_trash` undoes it for 30 days.
- **Stateless HTTP.** Each request is independent, which suits scale-to-zero hosting like Cloud Run.
- **Registration by import.** `@google_mcp.tool` registers a function when its module is imported,
  so `main.py` is the single place that lists which modules are part of the server.

## Quick start (local)

Needs Python 3.12+, `make`, and a Google account.

1. **Create an OAuth client.** In the [Google Cloud console](https://console.cloud.google.com):
   create a project, enable the **Google Tasks API** and **Gmail API**, and create an **OAuth client ID** of type
   *Desktop app*. Download the JSON as `client_secret.json` in the repo root. Set the app's
   publishing status to *In production*, otherwise refresh tokens expire after 7 days.
2. **Install and sign in:**
   ```
   make deps
   make env      # opens the browser, generates MCP_SECRET, writes env.yaml
   make run      # starts the server and prints the URL
   ```
3. **Connect Claude Code:**
   ```
   claude mcp add --transport http keep-tasks http://localhost:8080/<MCP_SECRET>/mcp
   ```
   Then ask it to list your task lists.

### Gmail

`make env` asks for Tasks and Gmail access on the same consent screen. Gmail's `gmail.modify` is a
restricted scope, so Google shows an "unverified app" warning for your own client; choose
*Advanced -> Go to (app)* to continue. If you signed in before Gmail support was added, run
`make env` again (and redeploy) to get a refresh token that includes Gmail.

A typical cleanup:

1. `gmail_top_senders` (default query `category:promotions is:unread`) lists the biggest senders.
2. `gmail_bulk_trash(query="from:deals@shop.com")` dry run: count plus a sample to check.
3. `gmail_bulk_trash(..., dry_run=false)` trashes them all. Starred mail is skipped.

### Optional: Google Keep

Google offers no Keep API for personal accounts. `gkeepapi` reverse-engineers the Android app
using a master token that grants broad access to your Google account, and Google can break it at
any time. Treat that token like a password. Keep is opt-in: leave `KEEP_*` unset and the Keep
tools simply report that Keep isn't configured.

```
make env-keep   # walks you through getting the master token
```

## Deploy to Google Cloud Run

```
make gcloud-install
make gcloud-setup PROJECT=<your-project-id>   # login + enable APIs (billing must be linked)

gcloud run deploy keep-tasks-mcp --source . --region europe-west1 \
  --allow-unauthenticated --env-vars-file env.yaml --max-instances 1 --memory 512Mi

make url PROJECT=<your-project-id>            # prints the connector URL
```

Cloud Build builds the `Dockerfile` remotely, so Docker doesn't need to be running locally. Add the
printed URL in claude.ai under **Settings -> Connectors -> Add custom connector**.

## Security model

- The service is public and the only protection is the secret in the URL path
  (`/<MCP_SECRET>/mcp`, 24+ random characters). Don't share the URL. To rotate it, change
  `MCP_SECRET` and redeploy.
- Credentials live in `env.yaml` / `.env`, both git-ignored. They are passed to Cloud Run as
  environment variables.
- This is a personal-use setup. For multiple users, put real sign-in in front of it, for example
  FastMCP's `GoogleProvider` OAuth.

## Tech Stack

Python, [FastMCP](https://gofastmcp.com), Google API Python client (Tasks, Gmail), `gkeepapi`, Docker, Google Cloud Run.

## About me

![Grigor Stoyanov](https://user-images.githubusercontent.com/76039296/217279449-93faa114-667a-4183-96cb-60d5393da610.png)

**Grigor Stoyanov**: [LinkedIn](https://www.linkedin.com/in/grigor-stoyanov-b5ab791aa/?isSelfProfile=true) · [GitHub](https://github.com/grigor-stoyanov)

## License

[MIT](LICENSE)
