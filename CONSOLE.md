# AzureRedOps Console

A self-hosted web GUI around the [AzureRedOps](AzureRedOps.py) red-team toolkit
(Mr.Un1k0d3r, TrueCyber Inc). It turns the CLI into a FastAPI backend + React
frontend + PostgreSQL database so you can run engagements from a browser and keep
a record of past assessments.

> ⚠️ **Authorized, educational use only.** This tool performs live authentication,
> password spraying, and Microsoft Graph actions against Azure / Entra ID tenants.
> Only use it against environments you are explicitly authorized to test.

---

## Architecture

```
                 ┌──────────────┐      /api/*      ┌───────────────────────┐
  browser  ─────▶│  frontend    │ ───────────────▶ │  backend (FastAPI)     │
                 │  nginx + SPA │                  │  - JWT auth            │
                 └──────────────┘                  │  - job engine (threads)│
                                                   │  - RedOpsService core  │──▶ Azure / Graph
                                                   └───────────┬───────────┘
                                                               │
                                                       ┌───────▼───────┐
                                                       │  PostgreSQL    │
                                                       │  assessments,  │
                                                       │  tokens, jobs, │
                                                       │  job logs      │
                                                       └────────────────┘
```

| Component | Path | Notes |
|-----------|------|-------|
| Core service | [backend/app/core/redops.py](backend/app/core/redops.py) | Refactor of `AzureRedOps.py` — returns structured data and streams log events instead of `print()`/`input()`. |
| Browser flows | [backend/app/core/browser.py](backend/app/core/browser.py) | PKCE callback + HAR/Playwright token capture. |
| API | [backend/app/routers/](backend/app/routers) | auth, assessments, tokens (vault), operations, jobs, reference. |
| Job engine | [backend/app/jobs.py](backend/app/jobs.py) | Runs activities in worker threads, persists log lines, supports cancellation. |
| Frontend | [frontend/src/](frontend/src) | React + Vite + TypeScript. |
| MCP server | [mcp_server/](mcp_server) | Remote Streamable-HTTP MCP server wrapping the API as tools. |

The original `AzureRedOps.py` CLI is untouched and still works standalone.

**Docs:** the full HTTP API reference (endpoints, schemas, per-activity params, SSE
stream) is in [API.md](API.md). The MCP server is documented in
[mcp_server/README.md](mcp_server/README.md).

---

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env — at minimum set ADMIN_PASSWORD, POSTGRES_PASSWORD and SECRET_KEY.

docker compose up --build -d
```

Open **http://localhost:8080** and log in with the admin credentials from `.env`.

Generate strong secrets:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"            # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # VAULT_KEY
```

---

## How it maps to the CLI

Every `--activity` from the CLI is exposed as an **operation** in the UI,
grouped into Reconnaissance, Authentication, Password Spraying, and Actions.
The form fields for each operation are served from `/api/catalog`, so the UI
renders inputs dynamically.

| CLI activity | UI operation |
|---|---|
| `id` | Tenant ID lookup |
| `auth`, `phish-start`, `phish-capture`, `refresh`, `auth-app`, `auth-interactive` | Authentication group |
| `self`, `permission`, `email`, `list-users`, `list-applications`, `list-principals`, `gather-all`, `raw-url`, `magic-app` | Reconnaissance group |
| `spray`, `spray-refresh` | Password Spraying group |
| `register-app`, `new-group`, `add-group`, `invite`, `push-file` | Actions group |
| `knownids`, `interest`, `list-interest` | Reference page |
| `save`, `list-token`, `view`, `delete` | Token Vault tab (per assessment) |

### Workflow

1. **Create an assessment** (engagement) on the dashboard.
2. Run **operations** from the Operations tab. Long-running jobs (spray,
   gather-all, device-code capture, browser flows) stream output live and can be
   cancelled.
3. Token-producing operations can **auto-save the resulting token to the vault**
   (tokens are encrypted at rest with the Fernet `VAULT_KEY`).
4. Re-use stored tokens in later operations by selecting them in the "Vault token"
   dropdown instead of pasting a raw token.
5. Every run is recorded under **Jobs** with its full log and JSON result.
6. **Archive** finished assessments — they stay searchable for historical reference.

---

## Browser-based flows

- **PKCE (`auth-app`)** — the job prints a consent URL to the live console. Open it,
  authenticate, and the local TLS callback (published on `https://localhost:2342`)
  captures the authorization code. Uses the bundled cert in `includes/web/`.
- **Interactive (`auth-interactive`)** — the backend image is built on the official
  Playwright image, so Chromium is available. Tokens are scraped from the session
  HAR. Headless capture works for unattended flows; interactive auth needs a
  display (set `PLAYWRIGHT_HEADLESS=0` and attach a VNC sidecar if you need to
  click through MFA manually).

---

## MCP server (drive the console from an AI agent)

The stack includes a remote **MCP server** (`mcp` service) that exposes the whole API as
Model Context Protocol tools over Streamable HTTP, so an MCP client on your machine can run
assessments, operations, and the token vault.

```bash
# In .env, set a bearer token:
python3 -c "import secrets;print(secrets.token_urlsafe(32))"   # -> MCP_API_KEY

docker compose up --build -d        # mcp endpoint: http://127.0.0.1:9090/mcp
```

Connect a client (e.g. Claude Code):

```bash
claude mcp add --transport http azureredops http://127.0.0.1:9090/mcp \
  --header "Authorization: Bearer <your MCP_API_KEY>"
```

The port is published on `127.0.0.1` only and gated behind the bearer token. See
[mcp_server/README.md](mcp_server/README.md) for the full tool list and config.

---

## Local development (no Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium            # only needed for auth-interactive
export DATABASE_URL="sqlite:///./dev.db"   # or a Postgres URL
export AZUREREDOPS_INCLUDES="$(cd .. && pwd)/includes"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # proxies /api to http://localhost:8000
```

Run the offline smoke test (SQLite, no network):

```bash
cd backend && python smoke_test.py
```

---

## Security notes

- Single admin account, bootstrapped from `ADMIN_USERNAME`/`ADMIN_PASSWORD` on
  first start. Change the password and rotate `SECRET_KEY` before exposing it.
- Captured access/refresh tokens are encrypted at rest (Fernet). Set a dedicated
  `VAULT_KEY` so rotating `SECRET_KEY` doesn't lock you out of stored tokens.
- The API is only reachable through the frontend's nginx proxy by default; the
  backend port is not published. Bind the stack to a trusted network.
- Do not commit `.env`, the SQLite db, `*.har`, or `.azure_creds`.
```
