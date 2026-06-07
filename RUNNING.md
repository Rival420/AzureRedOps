# Running the stack & MCP server

A short operator guide. Everything is driven by **`./azureredops.sh`** (run
`./azureredops.sh help` for all commands). Full API docs: [API.md](API.md);
MCP details: [mcp_server/README.md](mcp_server/README.md).

---

## 1. First run (3 commands)

```bash
./azureredops.sh init-secrets     # generate .env with strong secrets + an MCP_API_KEY
./azureredops.sh up --build       # build images and start db + backend + frontend + mcp
./azureredops.sh health           # verify db / backend / mcp are healthy
```

`init-secrets` prints the credentials you need (also saved in `.env`, chmod 600):

```
Console UI    : http://localhost:8080
Console login : admin / <generated password>
MCP endpoint  : http://127.0.0.1:9090/mcp
MCP_API_KEY   : <generated key>
```

Reprint them anytime with `./azureredops.sh creds`.

---

## 2. The MCP server

It runs as the `mcp` service, published on **`127.0.0.1:9090`** (your machine only),
speaks **Streamable HTTP** at `/mcp`, and requires the `MCP_API_KEY` as a bearer token.

### Generate / view / rotate the API key

| Action | Command |
|---|---|
| Key is generated automatically by | `./azureredops.sh init-secrets` |
| Print the current key + connection config | `./azureredops.sh mcp-info` |
| Generate a brand-new key and apply it | `./azureredops.sh rotate-mcp-key` |

> Generate one by hand if you prefer: `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`
> then set `MCP_API_KEY=...` in `.env` and run `./azureredops.sh restart mcp`.

### Connect a client

`./azureredops.sh mcp-info` prints both of these, filled in with your key:

**Claude Code**

```bash
claude mcp add --transport http azureredops http://127.0.0.1:9090/mcp \
  --header "Authorization: Bearer <MCP_API_KEY>"
```

**`.mcp.json`**

```json
{
  "mcpServers": {
    "azureredops": {
      "type": "http",
      "url": "http://127.0.0.1:9090/mcp",
      "headers": { "Authorization": "Bearer <MCP_API_KEY>" }
    }
  }
}
```

### Quick check without a client

```bash
KEY=$(grep ^MCP_API_KEY= .env | cut -d= -f2)
# No token -> 401 (the bearer gate). With the token, initialize succeeds:
curl -s -H "Authorization: Bearer $KEY" \
     -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
     http://127.0.0.1:9090/mcp
```

Once connected, start with the **`redops_get_catalog`** tool to discover the available
operations, then `redops_create_assessment` → `redops_run_operation_and_wait`.

---

## 3. Day-to-day admin commands

```bash
./azureredops.sh status            # what's running + URLs
./azureredops.sh logs mcp -f       # follow a service's logs
./azureredops.sh restart mcp       # restart one service
./azureredops.sh update            # pull base images, rebuild, recreate
./azureredops.sh backup            # pg_dump -> backups/<timestamp>.dump
./azureredops.sh restore <file>    # restore a dump (overwrites current data)
./azureredops.sh psql              # open a psql shell
./azureredops.sh down              # stop (keeps data volume)
./azureredops.sh nuke              # stop AND delete the data volume (asks first)
```

Add `--yes` to skip confirmation prompts on `nuke` / `restore`.

---

## 4. Notes

- Regenerating secrets (`init-secrets --force`) changes `POSTGRES_PASSWORD`, which only
  takes effect on a fresh database — run `nuke` first if you want a clean slate.
- The MCP server logs into the backend as the **admin** account, so any client holding
  `MCP_API_KEY` has full console privileges. Keep the key secret; rotate it if leaked.
- Authorized, educational security testing only.
```
