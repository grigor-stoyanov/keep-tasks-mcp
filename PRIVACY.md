# Privacy Policy

_Last updated: 2026-10-27_

## What this is

Keep Tasks MCP is a small open-source tool for **personal use**. It lets an AI assistant that you
connect to it read and manage your own Google Tasks and Google Keep notes, and clean up your Gmail. It is not a hosted
service and has no user accounts. Anyone who uses it runs their own copy, with their own Google
credentials, on their own computer or their own Google Cloud project.

The author does not operate a server that receives your data and cannot see it.

## Data the tool accesses

When you sign in with Google and grant access, the tool can:

- **Google Tasks**: read, create, update and delete your task lists and tasks.
- **Gmail**: search your mail, read message headers (sender, subject, date, unsubscribe link) and
  move messages to and from Trash. It does not read message bodies, send mail, or permanently delete.
- **Google Keep** (optional, via an unofficial library): read, create, edit, archive and trash your notes
  and checklists.
- **Outlook.com** (optional, via Microsoft Graph): list, search and read your mail (including message
  bodies), mail folders, attachment names and calendar events. Its access is read-only: it cannot send,
  move, delete or change anything.

It only does these things when the AI assistant you connected asks it to, in response to your requests.

## What is stored and where

- **Credentials** (a Google refresh token and, if you enable them, a Keep master token and a Microsoft
  refresh token) are stored as
  environment variables in your own deployment, or in a local `env.yaml` file on your computer.
- **Your tasks, notes and email** are not copied into any database, file or log by this tool. They pass through
  to the AI assistant you connected, and nowhere else.
- **Platform logs.** If you deploy to Google Cloud Run, Google's platform keeps standard request
  logs for your project. That is controlled by you, in your Google Cloud project.

## The shared server (if a friend invited you)

The repository also contains an optional shared server (`multiuser/`) that its owner can run for
up to 10 invited friends. If you sign in to someone else's copy, it works differently from the
personal setup above:

- **Who runs it.** The person who invited you operates the server in their own Google Cloud project.
  They are responsible for it, not the author of this software (unless the author invited you).
- **Who can use it.** Only email addresses the owner has added. If you aren't on the list, the
  sign-in is refused and the tokens Google just issued are revoked straight away, so nothing of
  yours is kept.
- **What is stored.** Your Google email address, your Google access and refresh tokens, and, only
  if you link Outlook, your Microsoft refresh token. They are kept in the owner's Firestore
  database, encrypted with a key only the server holds. A daily count of your tool calls is kept
  for two days to enforce usage limits.
- **What is not stored.** The contents of your tasks, notes and email. They pass through to the AI
  app you connected, as with the personal setup.
- **What the owner can technically do.** Whoever controls the server and its key could in principle
  use the stored tokens to access the services you granted. Only use a shared server run by someone
  you trust.
- **Your choices.** You can untick Tasks or Gmail on Google's consent screen; those tools then stay
  hidden. Outlook is only linked if you ask for it, and is read-only.
- **Removing your data.** Ask your AI app to run `outlook_disconnect` to delete your Microsoft token.
  Revoke the server's access at <https://myaccount.google.com/permissions> (Google) and
  <https://account.live.com/consent/Manage> (Microsoft), and ask the owner to remove you from the
  list. Stored Google tokens stop working as soon as you revoke them, and are deleted from storage
  automatically within a year.

## Sharing

The tool does not sell, share or transfer your data to anyone, and has no analytics, advertising or
tracking. Data goes only between Google, your own deployment, and the AI assistant you chose to connect.
What that assistant does with the data is governed by that assistant's own privacy policy.

## Google API Services User Data Policy

This tool's use and transfer of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements. Data is used only to provide the features you ask for.

## Your control

- **Revoke access** at any time at <https://myaccount.google.com/permissions> (Google) and
  <https://account.live.com/consent/Manage> (Microsoft).
- **Delete everything** by deleting your deployment and your local `env.yaml`.
- **Rotate the connector URL** by changing `MCP_SECRET` and redeploying.

## Security note

Anyone who has your connector URL, or your Google refresh token or Keep master token, can access your
tasks, notes and email. Keep them private. The Keep master token grants broad access to your Google account.

## Contact

Questions: open an issue at <https://github.com/grigor-stoyanov/keep-tasks-mcp/issues>.
