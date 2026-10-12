# Google Keep + Tasks MCP server

A remote MCP server (Streamable HTTP) that you add to Claude as a **custom connector**.
13 tools: `tasks_*` (official Google Tasks API) and `keep_*` (unofficial, via `gkeepapi`).

> **Keep caveat:** Google offers no Keep API for personal @gmail.com accounts. `gkeepapi`
> reverse-engineers the Android app's protocol using a "master token" that grants broad access
> to your Google account. It works, but Google can break it at any time. Treat
> `KEEP_MASTER_TOKEN` like your password. Keep is optional: leave those vars unset to disable it.

## 1. Google Tasks credentials (about 5 min)

1. https://console.cloud.google.com: create a project (e.g. `claude-mcp`).
2. **APIs & Services → Library**: enable **Google Tasks API**.
3. **Google Auth Platform → Branding**: fill in the app name and your email. **Audience**: External,
   then click **Publish app** (set it to *In production*). In *Testing* mode, refresh tokens expire after 7 days.
4. **Clients → Create client → Desktop app**, then download the JSON as `client_secret.json`.
5. Get the refresh token (a browser opens; click *Advanced → continue* on the "unverified app" screen):
   ```
   pip install google-auth-oauthlib
   python scripts/get_tasks_token.py client_secret.json
   ```

## 2. Google Keep credentials (optional)

Follow the steps at the top of `scripts/get_keep_token.py`, then:
```
pip install gpsoauth
python scripts/get_keep_token.py you@gmail.com
```

## 3. Deploy to Google Cloud Run (always reachable, free tier is enough)

Install the gcloud CLI (`winget install Google.CloudSDK`), or use **Cloud Shell** in the console,
where gcloud is already installed. Then create `env.yaml` (it is git-ignored):

```yaml
MCP_SECRET: "<python -c "import secrets;print(secrets.token_urlsafe(32))">"
GOOGLE_CLIENT_ID: "..."
GOOGLE_CLIENT_SECRET: "..."
GOOGLE_REFRESH_TOKEN: "..."
KEEP_EMAIL: "you@gmail.com"
KEEP_MASTER_TOKEN: "aas_et/..."
```

```
gcloud auth login
gcloud config set project <your-project-id>
gcloud run deploy keep-tasks-mcp --source . --region europe-west1 \
  --allow-unauthenticated --env-vars-file env.yaml --max-instances 1 --memory 512Mi
```

Cloud Build builds the Dockerfile remotely, so you don't need Docker running locally. The command prints
`https://keep-tasks-mcp-xxxx.a.run.app`.

## 4. Add to Claude

claude.ai → **Settings → Connectors → Add custom connector**:
URL = `https://keep-tasks-mcp-xxxx.a.run.app/<MCP_SECRET>/mcp`

Connectors added on claude.ai also work in the Claude desktop and mobile apps. For Claude Code:
```
claude mcp add --transport http keep-tasks https://keep-tasks-mcp-xxxx.a.run.app/<MCP_SECRET>/mcp
```

## Security model

The URL secret is the only protection, so don't share the URL. To rotate it, change `MCP_SECRET`
and redeploy. If you want real per-user sign-in, put it behind FastMCP's `GoogleProvider` OAuth.

## Run locally

```
pip install -r requirements.txt
# set the env vars from .env.example, then:
python server.py      # http://localhost:8080/<MCP_SECRET>/mcp
```
