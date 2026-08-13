# Abdul Sattar Woods — Business Management System

A timber-trading accounting system, delivered as **three independent apps that
share one online database**:

| Folder | App | Notes |
|--------|-----|-------|
| [`desktop/`](desktop/) | Windows desktop (PySide6) | Full read/write. Also holds the shared business logic + the cloud API that mobile and the website use. |
| [`mobile/`](mobile/) | Flutter app | Talks to the cloud API. |
| [`website/`](website/) | Web app | In progress. Will talk to the cloud API (full read/write). |

## Independence

Each app runs on its own — **none depends on another app being up**. They all
connect to the same hosted database, and mobile + website go through the
always-on cloud API. So the website works whether or not the desktop PC is on,
and the desktop app works on its own.

```
Abdul Sattar Woods/
├─ desktop/     Python project: timber/ (core · db · ui · api), alembic/, tests, build
├─ mobile/      Flutter client
├─ website/     web client (to be built)
└─ render.yaml  deploys the cloud API (built from desktop/) to the cloud
```

## Deploy

`render.yaml` lives at the repo root (Render auto-detects it) and builds the
cloud API from `desktop/` (`dockerContext: ./desktop`). The API self-migrates
the database to the latest schema on startup.

See [`desktop/README.md`](desktop/README.md) for desktop build/run details.
