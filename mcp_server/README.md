# AzureRedOps MCP Server

A **remote MCP (Model Context Protocol) server** that exposes the
[AzureRedOps Console](../CONSOLE.md) REST API (see [API.md](../API.md)) as MCP tools over
the **Streamable HTTP** transport. Run it as part of the Docker stack and connect to it
from an MCP client on your local machine.

```
MCP client  ──(Authorization: Bearer MCP_API_KEY)──▶  mcp service  ──(admin JWT)──▶  backend (FastAPI)  ──▶  Azure / Graph
   (your machine)         http://127.0.0.1:9090/mcp        :9000                         :8000
```

The MCP server is a thin, stateless client of the backend. It authenticates to the
backend once with the console admin credentials and caches the JWT (re-authenticating
automatically on expiry), so MCP clients only need the single `MCP_API_KEY` bearer token.

> ⚠️ **Authorized, educational use only.** These tools trigger live authentication,
> password spraying, and Microsoft Graph actions. Several are destructive. Use only
> against tenants you are explicitly authorized to test.

---

## Tools

| Tool | Kind | Purpose |
|---|---|---|
| `redops_health` | read | Backend health check |
| `redops_whoami` | read | Confirm the backend principal |
| `redops_list_assessments` / `redops_get_assessment` | read | Browse engagements |
| `redops_create_assessment` / `redops_update_assessment` | write | Manage engagements |
| `redops_archive_assessment` / `redops_restore_assessment` | write | Archive lifecycle |
| `redops_delete_assessment` | **destructive** | Delete an engagement + its data |
| `redops_list_vault_tokens` | read | List stored tokens (metadata only) |
| `redops_add_vault_token` | write | Store a captured token (encrypted) |
| `redops_reveal_vault_token` | read (sensitive) | Decrypt a stored token + claims |
| `redops_delete_vault_token` | **destructive** | Remove a stored token |
| `redops_get_catalog` | read | **Discover** activities and their params |
| `redops_run_operation` | **live / destructive** | Submit an operation as an async job |
| `redops_run_operation_and_wait` | **live / destructive** | Submit + wait for the result |
| `redops_list_jobs` / `redops_get_job` / `redops_get_job_logs` | read | Inspect jobs |
| `redops_wait_for_job` | read | Poll a job until terminal |
| `redops_cancel_job` | write | Cancel a long-running job |
| `redops_reference_known_ids` / `redops_reference_interest` | read | Bundled reference data |

Always call `redops_get_catalog` first to learn which `activity` values exist and what
`params` each one needs.

---

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `BACKEND_URL` | `http://backend:8000` | Base URL of the FastAPI backend |
| `ADMIN_USERNAME` | `admin` | Console admin user the server logs in as |
| `ADMIN_PASSWORD` | `changeme` | Console admin password |
| `MCP_API_KEY` | *(empty)* | Bearer token MCP clients must present. **Set this.** |
| `MCP_HOST` | `0.0.0.0` | Bind address inside the container |
| `MCP_PORT` | `9000` | Listen port inside the container |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_HTTP_TIMEOUT` | `180` | Per-request timeout (s) to the backend |

In the compose stack the container port `9000` is published to **`127.0.0.1:${MCP_PORT}`**
(default `9090`) — reachable from this machine only, not the LAN.

If `MCP_API_KEY` is unset the server logs a warning and serves **unauthenticated**
(still localhost-bound). Always set a key before relying on it.

---

## Run it (Docker)

```bash
cp .env.example .env          # set ADMIN_PASSWORD, POSTGRES_PASSWORD, SECRET_KEY, MCP_API_KEY
python3 -c "import secrets;print(secrets.token_urlsafe(32))"   # -> MCP_API_KEY

docker compose up --build -d mcp     # (brings up db + backend too)
```

The MCP endpoint is then at `http://127.0.0.1:9090/mcp`.

---

## Connect a client

The server speaks **Streamable HTTP** and requires an `Authorization: Bearer` header.

**Claude Code** (or any client that supports remote HTTP MCP with headers):

```bash
claude mcp add --transport http azureredops \
  http://127.0.0.1:9090/mcp \
  --header "Authorization: Bearer <your MCP_API_KEY>"
```

**`.mcp.json` / client config** style:

```json
{
  "mcpServers": {
    "azureredops": {
      "type": "http",
      "url": "http://127.0.0.1:9090/mcp",
      "headers": { "Authorization": "Bearer <your MCP_API_KEY>" }
    }
  }
}
```

**Inspect/debug** with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
# Transport: Streamable HTTP, URL http://127.0.0.1:9090/mcp,
# add header Authorization: Bearer <your MCP_API_KEY>
```

---

## Local development (no Docker)

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export BACKEND_URL=http://localhost:8000   # a running backend
export ADMIN_USERNAME=admin ADMIN_PASSWORD=changeme
export MCP_API_KEY="dev-key"
export MCP_PORT=9090
python server.py
# -> http://0.0.0.0:9090/mcp
```

> Note: the directory is `mcp_server/` (not `mcp/`) on purpose — a top-level `mcp/`
> directory would shadow the installed `mcp` PyPI package on `sys.path`.
