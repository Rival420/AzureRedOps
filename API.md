# AzureRedOps Console — HTTP API Reference

Complete reference for the FastAPI backend that powers the [AzureRedOps Console](CONSOLE.md).
Every endpoint, request/response schema, the operation catalog, per-activity parameters,
the live job stream, and error shapes are documented below.

> ⚠️ **Authorized, educational use only.** This API drives live authentication,
> password spraying, and Microsoft Graph actions against Azure / Entra ID tenants.

The API is also browsable interactively — FastAPI serves auto-generated docs:

| Tooling | Path |
|---|---|
| Swagger UI | `GET /docs` |
| ReDoc | `GET /redoc` |
| OpenAPI JSON | `GET /openapi.json` |

This document adds what the auto-generated schema **cannot** express: the per-activity
shape of `OperationRequest.params` (a free-form object validated only by the operation
catalog), the SSE event format, and worked examples.

---

## 1. Base URL & networking

| Context | Base URL |
|---|---|
| Through the frontend nginx proxy (default deployment) | `http://localhost:8080/api` |
| Directly against the backend container (if port `8000` is published) | `http://localhost:8000/api` |
| From another container on the compose network | `http://backend:8000/api` |

All paths below are written **relative to the host root** and include the `/api` prefix
(e.g. `POST /api/auth/login`).

---

## 2. Authentication

The API uses **OAuth2 password flow → JWT bearer**. There is a single admin user,
bootstrapped from `ADMIN_USERNAME` / `ADMIN_PASSWORD` on first startup.

### `POST /api/auth/login`

Exchange credentials for an access token. **Body is `application/x-www-form-urlencoded`**
(OAuth2 `password` grant), not JSON.

**Request (form fields)**

| Field | Type | Required | Notes |
|---|---|---|---|
| `username` | string | yes | |
| `password` | string | yes | |
| `grant_type` | string | no | optional, `password` |

**Response `200` — `TokenResponse`**

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "username": "admin"
}
```

**Errors:** `401` — `{"detail": "Incorrect username or password"}`

**Example**

```bash
curl -s -X POST http://localhost:8080/api/auth/login \
  -d 'username=admin' -d 'password=changeme'
```

### Authenticating subsequent requests

Send the token as a bearer header on **every** other endpoint:

```
Authorization: Bearer <access_token>
```

Token lifetime is `ACCESS_TOKEN_MINUTES` (default 720). On expiry/invalid token, all
protected endpoints return `401 {"detail": "Could not validate credentials"}` with a
`WWW-Authenticate: Bearer` header.

### `GET /api/auth/me`

Returns the current principal. **Auth required.**

```json
{ "username": "admin", "is_admin": true }
```

---

## 3. Conventions

- **Content type:** request and response bodies are JSON, except the login form above.
- **Timestamps:** ISO-8601 strings (UTC) in responses; token `expires` is a Unix epoch int.
- **Errors:** FastAPI's standard shape — `{"detail": "..."}` for `4xx`, or a list of
  field errors for `422` validation failures:
  ```json
  { "detail": [ { "loc": ["body","name"], "msg": "field required", "type": "value_error.missing" } ] }
  ```
- **Auth:** every endpoint **except** `POST /api/auth/login` and `GET /api/health`
  requires a bearer token.

---

## 4. Health

### `GET /api/health` — *no auth*

```json
{ "status": "ok", "service": "azureredops-console" }
```

---

## 5. Assessments

An **assessment** is an engagement container that owns vault tokens and jobs.
All routes require auth.

| Method | Path | Description | Success |
|---|---|---|---|
| `GET` | `/api/assessments` | List assessments (optional `?status=`) | `200` |
| `POST` | `/api/assessments` | Create an assessment | `201` |
| `GET` | `/api/assessments/{assessment_id}` | Get one | `200` |
| `PATCH` | `/api/assessments/{assessment_id}` | Partial update | `200` |
| `POST` | `/api/assessments/{assessment_id}/archive` | Set status `archived` | `200` |
| `POST` | `/api/assessments/{assessment_id}/restore` | Set status `active` | `200` |
| `DELETE` | `/api/assessments/{assessment_id}` | Delete (cascades tokens + jobs) | `204` |

**Query params (`GET /api/assessments`)**

| Param | Type | Notes |
|---|---|---|
| `status` | string | filter, e.g. `active` / `archived` |

**`AssessmentCreate` (request body for POST)**

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `client` | string \| null | no |
| `description` | string \| null | no |
| `scope_notes` | string \| null | no |

**`AssessmentUpdate` (request body for PATCH)** — all fields optional; only supplied
fields are changed: `name`, `client`, `description`, `scope_notes`, `status`.

**`AssessmentOut` (response)**

```json
{
  "id": 1,
  "name": "Acme Q2 Engagement",
  "client": "Acme Corp",
  "description": "External Entra ID assessment",
  "scope_notes": "tenant acme.onmicrosoft.com only",
  "status": "active",
  "created_at": "2026-06-07T10:30:00",
  "updated_at": "2026-06-07T10:30:00",
  "token_count": 0,
  "job_count": 0
}
```

**Errors:** `404 {"detail": "Assessment not found"}` for unknown IDs.

---

## 6. Token vault

Captured access/refresh tokens, **encrypted at rest** (Fernet `VAULT_KEY`). Scoped under
an assessment. All routes require auth.

Base path: `/api/assessments/{assessment_id}/tokens`

| Method | Path | Description | Success |
|---|---|---|---|
| `GET` | `` (base) | List vault tokens for the assessment | `200` |
| `POST` | `` (base) | Store a new token | `201` |
| `GET` | `/{token_id}/reveal` | Decrypt and return the raw token + claims | `200` |
| `DELETE` | `/{token_id}` | Delete a token | `204` |

**`TokenCreate` (request body)**

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | label |
| `access_token` | string | yes | raw JWT; claims (`tid`,`upn`,`scp`,`aud`,`exp`) are auto-extracted |
| `refresh_token` | string \| null | no | |
| `tenant_id` | string \| null | no | overrides `tid` claim if set |
| `username` | string \| null | no | overrides `upn`/`unique_name` claim if set |

**`TokenOut` (response — never includes the raw token)**

```json
{
  "id": 5,
  "assessment_id": 1,
  "name": "user1 graph token",
  "tenant_id": "8a...e1",
  "username": "user1@acme.com",
  "scope": "User.Read Mail.Read",
  "audience": "https://graph.microsoft.com",
  "expires": 1749300000,
  "expires_human": "2026-06-07 12:00:00",
  "is_expired": false,
  "created_at": "2026-06-07T10:40:00"
}
```

**`TokenReveal` (response from `/reveal` — sensitive)**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "0.AX...",
  "claims": { "tid": "...", "upn": "...", "scp": "...", "aud": "...", "exp": 1749300000 }
}
```

**Errors:** `404 {"detail": "Assessment not found"}` (create), `404 {"detail": "Token not found"}`
(reveal/delete; also returned if the token exists but belongs to a different assessment).

---

## 7. Operation catalog

### `GET /api/catalog` — *auth required*

Returns the full, machine-readable description of every operation grouped into sections.
The frontend renders input forms from this; **API/MCP consumers should use it to discover
valid `activity` values and their `params` keys**.

**Response shape**

```json
[
  {
    "key": "recon",
    "title": "Reconnaissance",
    "operations": [
      {
        "activity": "id",
        "name": "Tenant ID lookup",
        "long_running": false,
        "description": "Resolve the Azure tenant ID from a domain name.",
        "fields": [
          {
            "name": "tenant",
            "label": "Tenant domain",
            "type": "text",
            "required": true,
            "placeholder": "contoso.com",
            "help": "",
            "default": null,
            "options": []
          }
        ]
      }
    ]
  }
]
```

**Field object schema**

| Key | Type | Meaning |
|---|---|---|
| `name` | string | the key to place in `OperationRequest.params` |
| `label` | string | human label |
| `type` | enum | `text` \| `password` \| `textarea` \| `number` \| `bool` \| `token` \| `select` |
| `required` | bool | whether the param is mandatory |
| `placeholder` | string | example value |
| `help` | string | guidance |
| `default` | any \| null | default value |
| `options` | string[] | choices when `type=select` |

A field of `type: "token"` (always named `token_id`) means "pick a stored vault token";
operations that accept it also accept a raw `access_token` string instead.

---

## 8. Running operations (jobs)

### `POST /api/assessments/{assessment_id}/operations` — *auth required*

Submits an operation as an **asynchronous job** that runs in a backend worker thread.
Returns immediately with `202` and the created `Job` in `pending`/`running` state — poll
`GET /api/jobs/{id}` or subscribe to the SSE stream for progress and the final result.

**`OperationRequest` (request body)**

| Field | Type | Default | Notes |
|---|---|---|---|
| `activity` | string | — | the operation key (see §9), e.g. `"spray"` |
| `params` | object | `{}` | activity-specific parameters (see §9) |
| `label` | string \| null | `activity` | display label for the job |
| `endpoint` | string \| null | null | override Microsoft endpoint host (e.g. `microsoftonline.com`) |
| `user_agent` | string \| null | null | override outbound User-Agent |
| `audience` | string \| null | null | override token audience |
| `scope` | string \| null | null | override OAuth scope |
| `use_beta` | bool | `false` | use the Graph `beta` endpoint |
| `additional_headers` | object\<string,string\> \| null | null | extra HTTP headers on Graph calls |
| `filters` | string[] \| null | null | response field filters |
| `check_privileges` | bool | `false` | on successful auth, probe for privileges |
| `save_token_as` | string \| null | null | if set and the activity yields a token, auto-store it in the vault under this name |

`save_token_as` only applies to **token-producing** activities:
`auth`, `phish-capture`, `refresh`, `auth-app`, `auth-interactive`.

**Response `202` — `JobOut`** (see §10).

**Errors:** `404 {"detail": "Assessment not found"}`.

**Example — start a password spray**

```bash
curl -s -X POST http://localhost:8080/api/assessments/1/operations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "activity": "spray",
        "label": "spray acme",
        "params": { "username": "user1@acme.com", "password": "Spring2026!", "tenant": "acme.com", "check_privileges": true }
      }'
```

---

## 9. Operations catalogue (activities & params)

Every `activity` accepted by `POST .../operations`, with its `params` keys. Items marked
**long-running** stream incremental log output and are cancellable. Activities that take a
token accept **either** `token_id` (a vault token id) **or** a raw `access_token` string in
`params`.

### Reconnaissance

| `activity` | Long-running | `params` | Description |
|---|---|---|---|
| `id` | no | `tenant` (req) | Resolve tenant ID from a domain. |
| `self` | no | `token_id`\|`access_token` | Current user Graph profile (`/me`). |
| `permission` | no | `token_id`\|`access_token` | Tenant authorization policy (beta). |
| `email` | no | token + `filter` (req, search term) | Search current user's mailbox. |
| `list-users` | yes | token + `filter` (OData, opt) | Enumerate directory users. |
| `list-applications` | yes | token + `filter` (OData, opt) | Enumerate app registrations. |
| `list-principals` | yes | token | Enumerate service principals. |
| `gather-all` | yes | token | Dump org, policies, users, groups, apps, grants, principals, roles. |
| `raw-url` | yes | token + `url` (req) | GET an arbitrary Graph URL (follows pagination). |
| `magic-app` | yes | token | Find public-client apps w/ AllPrincipals consent + no assignment requirement. |
| `inspect-token` | no | token | Decode the token's JWT claims locally. |

### Authentication

| `activity` | Long-running | `params` | Description |
|---|---|---|---|
| `auth` | no | `username` (req), `password` (req), `tenant` (req), `appid` (opt), `version` (`v2.0`\|`v0`, default `v2.0`) | ROPC username/password auth. |
| `phish-start` | no | `tenant` (opt, default `common`), `appid` (opt) | Generate a device code to present to a target. |
| `phish-capture` | yes | `device_code` (req), `tenant` (opt), `appid` (opt) | Poll for the token after the target authenticates. Cancellable. |
| `refresh` | no | `token_id` **or** `refresh_token`, `tenant` (if raw), `appid` (opt), `version` (default `v2.0`) | Exchange a refresh token for a fresh access token. |
| `auth-app` | yes | `tenant` (opt), `appid` (opt), `port` (opt, default 2342), `timeout` (s, default 300) | PKCE browser flow; prints a consent URL and captures the auth code on the local TLS callback. |
| `auth-interactive` | yes | `url` (req, default `https://portal.azure.com`), `delay` (s, default 75) | Playwright browser auth; tokens scraped from session HAR. Needs the Playwright display. |

### Password spraying

| `activity` | Long-running | `params` | Description |
|---|---|---|---|
| `spray` | yes | `username` (req), `password` (req), `tenant` (req), `check_privileges` (bool, default false) | Spray a credential across many first-party client IDs. Cancellable. |
| `spray-refresh` | yes | `token_id` **or** `refresh_token`, `tenant` (if raw), `check_privileges` (bool) | Replay a refresh token across many client IDs. Cancellable. |

### Privilege / persistence actions

| `activity` | Long-running | `params` | Description |
|---|---|---|---|
| `register-app` | no | token + `name` (req) | Create an app registration with a client secret. |
| `new-group` | no | token + `name` (req) | Create a security group. |
| `add-group` | no | token + `uid` (req, principal id), `gid` (opt, role def id; default Global Admin `62e90394-69f5-4237-91f9-056ad24d70a7`) | Assign a directory role to a principal. |
| `invite` | no | token + `email` (req), `url` (opt redirect) | Send a B2B guest invitation. |
| `push-file` | no | token + `name` (req filename), `content` (req) | Upload content to the user's OneDrive. |

> **Token resolution:** when both are present, `token_id` (the vault token) wins — the
> backend checks `token_id` first and only falls back to a raw `access_token` if it is
> unset. For refresh activities, a selected `token_id` supplies both the stored refresh
> token and its tenant.

---

## 10. Jobs

A **job** is one execution of an operation, with persisted log lines and a JSON result.
All routes require auth.

| Method | Path | Description | Success |
|---|---|---|---|
| `GET` | `/api/assessments/{assessment_id}/jobs` | List jobs (optional `?activity=`) → `JobSummary[]` | `200` |
| `GET` | `/api/jobs/{job_id}` | Get full job → `JobOut` | `200` |
| `GET` | `/api/jobs/{job_id}/logs` | Get log lines after `?after=<id>` → `JobLogOut[]` | `200` |
| `POST` | `/api/jobs/{job_id}/cancel` | Request cancellation | `200` |
| `GET` | `/api/jobs/{job_id}/stream` | **Server-Sent Events** stream of logs + terminal status | `200` (event stream) |

**Job status values:** `pending` → `running` → one of `completed` \| `failed` \| `cancelled`
(`awaiting_input` is reserved).

**`JobOut` (response)**

```json
{
  "id": 12,
  "assessment_id": 1,
  "activity": "spray",
  "label": "spray acme",
  "status": "completed",
  "params": { "username": "user1@acme.com", "tenant": "acme.com" },
  "result": { "valid": [ ... ] },
  "error": null,
  "created_at": "2026-06-07T11:00:00",
  "started_at": "2026-06-07T11:00:01",
  "finished_at": "2026-06-07T11:00:42"
}
```

**`JobSummary` (list response)** — `id`, `assessment_id`, `activity`, `label`, `status`,
`created_at`, `finished_at`.

**`JobLogOut`**

```json
{ "id": 88, "ts": "2026-06-07T11:00:05", "level": "info", "message": "Trying client id ..." }
```

`level` is one of `info` \| `success` \| `warning` \| `error` \| `action` \| `data`.

**`POST /api/jobs/{job_id}/cancel` response**

```json
{ "cancelled": true, "status": "running" }
```

`cancelled` is `true` if a cancel signal was delivered to a live worker; the job transitions
to `cancelled` shortly after at the next cancellation checkpoint.

**Polling pattern (without SSE):** call `GET /api/jobs/{id}/logs?after=<last_seen_id>`
repeatedly, advancing `after` to the highest `id` returned, until `GET /api/jobs/{id}`
reports a terminal status.

**Errors:** `404 {"detail": "Job not found"}`.

### 10.1 SSE stream — `GET /api/jobs/{job_id}/stream`

`Content-Type: text/event-stream`. Optional `?after=<id>` to resume after a log id.
Emits these named events:

| `event:` | `data:` payload | Meaning |
|---|---|---|
| `log` | `{"id","ts","level","message"}` | one new log line |
| `status` | `{"status": "completed"\|"failed"\|"cancelled"}` | terminal status; stream then closes |
| `error` | `{"message": "job not found"}` | stream aborts |
| *(comment)* | `: keep-alive` | heartbeat every ~1s while the job runs |

**Example (raw stream)**

```
event: log
data: {"id": 88, "ts": "2026-06-07T11:00:05", "level": "info", "message": "Trying client id ..."}

: keep-alive

event: status
data: {"status": "completed"}
```

---

## 11. Reference data

Static datasets bundled with the tool (no token needed). All routes require auth.

| Method | Path | Query | Description |
|---|---|---|---|
| `GET` | `/api/reference/known-ids` | `search`, `limit` (default 100), `offset` (default 0) | Catalogue of well-known first-party application IDs. |
| `GET` | `/api/reference/interest/categories` | — | Category names for "objects of interest". |
| `GET` | `/api/reference/interest` | `category` (opt) | Objects-of-interest entries, optionally filtered by category. |

**`GET /api/reference/known-ids` response**

```json
{
  "total": 412,
  "items": [
    { "name": "Microsoft Azure CLI", "appId": "04b07795-8ddb-461a-bbee-02f9e1bf7b46" }
  ]
}
```

---

## 12. Data model summary

| Model | Used by | Key fields |
|---|---|---|
| `TokenResponse` | login | `access_token`, `token_type`, `username` |
| `AssessmentCreate` / `AssessmentUpdate` / `AssessmentOut` | assessments | see §5 |
| `TokenCreate` / `TokenOut` / `TokenReveal` | vault | see §6 |
| `OperationRequest` | run operation | see §8 |
| `JobOut` / `JobSummary` / `JobLogOut` | jobs | see §10 |

---

## 13. End-to-end example

```bash
BASE=http://localhost:8080/api

# 1. Login
TOKEN=$(curl -s -X POST $BASE/auth/login -d 'username=admin' -d 'password=changeme' \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# 2. Create an assessment
AID=$(curl -s -X POST $BASE/assessments -H "$AUTH" -H 'Content-Type: application/json' \
      -d '{"name":"Demo","client":"Acme"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 3. Authenticate against the tenant and auto-save the token to the vault
JID=$(curl -s -X POST $BASE/assessments/$AID/operations -H "$AUTH" -H 'Content-Type: application/json' \
      -d '{"activity":"auth","save_token_as":"user1",
           "params":{"username":"user1@acme.com","password":"P@ss","tenant":"acme.com"}}' \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 4. Wait for the job, then read the result
curl -s $BASE/jobs/$JID -H "$AUTH"

# 5. List the vault tokens that resulted
curl -s $BASE/assessments/$AID/tokens -H "$AUTH"
```
