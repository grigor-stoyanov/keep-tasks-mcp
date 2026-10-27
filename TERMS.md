# Terms of Service

_Last updated: 2026-10-27_

Keep Tasks MCP is a small open-source project for **personal use**. By running it or signing in with
Google through it, you agree to the following.

## 1. What it is

This is software you run yourself, on your own computer or in your own Google Cloud project. It is
not a hosted service, and the author does not operate any server on your behalf. See the
[Privacy Policy](PRIVACY.md) for how data is handled.

## 2. Use at your own risk

The software is provided **"as is", without warranty of any kind**, as described in the
[MIT License](LICENSE). The author is not liable for any loss or damage, including lost, changed or
deleted tasks and notes. The tool can create, edit and delete data in your Google account when an AI
assistant you connected asks it to, so review what you allow it to do.

## 3. Google Keep is unofficial

Google offers no Keep API for personal accounts. The Keep features use an unofficial library that
imitates the Android app and requires a master token with broad access to your Google account.
It is not endorsed by Google, may stop working at any time, and its use may conflict with Google's
terms. You enable it at your own risk, and you are responsible for protecting that token.

## 4. Your responsibilities

- Keep your credentials and connector URL private. Anyone who has them can access your data.
- Follow the terms of the services you connect, including Google's terms and your AI assistant's terms.
- Do not use this software to access accounts or data that are not yours.

## 5. Shared servers

The optional shared server (`multiuser/`) lets one person host this software for a few invited
friends. If you use someone else's shared server:

- It is a free, informal favour between friends, not a service. It is provided as is, with no
  guarantee that it stays available.
- The owner sets the limits: who may sign in, which services are shared, and how many tool calls
  you get per day. They can change those limits or remove your access at any time.
- Don't try to get around the limits or use the server for anyone but yourself.
- The owner holds your sign-in tokens as described in the [Privacy Policy](PRIVACY.md). Only use a
  shared server run by someone you trust.

If you run a shared server, you are responsible for it: keep its `SERVER_KEY` and tokens secure,
invite only people you know, and tell them how their data is handled.

## 6. Changes

These terms may be updated. The latest version is in this repository.

## 7. Contact

Questions or issues: <https://github.com/grigor-stoyanov/keep-tasks-mcp/issues>.
