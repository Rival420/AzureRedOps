#!/usr/bin/env python3
"""Remote MCP server for the AzureRedOps Console.

Exposes the AzureRedOps Console REST API (see ../API.md) as Model Context Protocol
tools over the **Streamable HTTP** transport, so an MCP client on your local machine
can drive assessments, the token vault, operations/jobs, and reference data.

This server is a thin, authenticated client of the FastAPI backend:
  MCP client  --(bearer MCP_API_KEY)-->  this server  --(admin JWT)-->  backend (FastAPI)

Authorized, educational security testing only.
"""

import os
import sys
import json
import asyncio
import hmac
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Configuration (all from environment)
# --------------------------------------------------------------------------- #
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "").strip()
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "9000"))
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")
HTTP_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "180"))

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

mcp = FastMCP(
    "azureredops_mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    json_response=True,
    stateless_http=True,
)


# --------------------------------------------------------------------------- #
# Backend client: logs in with the admin account, caches the JWT, re-auths on 401
# --------------------------------------------------------------------------- #
class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class BackendClient:
    """Maintains a single authenticated httpx session against the FastAPI backend."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=HTTP_TIMEOUT)
        return self._client

    async def _login(self) -> None:
        client = await self._get_client()
        resp = await client.post(
            "/api/auth/login",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, _detail(resp) or "backend login failed")
        self._token = resp.json()["access_token"]

    async def _ensure_token(self) -> None:
        if self._token is None:
            async with self._lock:
                if self._token is None:
                    await self._login()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        await self._ensure_token()
        client = await self._get_client()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {self._token}"
        resp = await client.request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401:  # JWT expired/invalid — re-auth once and retry
            async with self._lock:
                await self._login()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await client.request(method, path, headers=headers, **kwargs)
        return resp


backend = BackendClient()


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _detail(resp: httpx.Response) -> Any:
    """Extract the FastAPI `detail` field (or raw text) from an error response."""
    try:
        body = resp.json()
        return body.get("detail", body) if isinstance(body, dict) else body
    except Exception:
        return resp.text


async def _api(method: str, path: str, **kwargs) -> Any:
    """Call the backend and return parsed JSON (or None for 204). Raises ApiError on 4xx/5xx."""
    resp = await backend.request(method, path, **kwargs)
    if resp.status_code >= 400:
        raise ApiError(resp.status_code, _detail(resp))
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _err(e: Exception) -> str:
    """Turn any exception into a concise, actionable error string for the agent."""
    if isinstance(e, ApiError):
        if e.status == 404:
            return f"Error 404: {e.detail}. Check the id is correct and the resource exists."
        if e.status == 401:
            return ("Error 401: the MCP server could not authenticate to the AzureRedOps "
                    "backend. Verify ADMIN_USERNAME / ADMIN_PASSWORD.")
        if e.status == 422:
            return f"Error 422 (validation): {e.detail}. Check required params via redops_get_catalog."
        return f"Error {e.status}: {e.detail}"
    if isinstance(e, httpx.ConnectError):
        return f"Error: cannot reach the AzureRedOps backend at {BACKEND_URL}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: the request to the AzureRedOps backend timed out."
    return f"Error: {type(e).__name__}: {e}"


def _operation_body(p: "RunOperationInput") -> dict:
    """Build an OperationRequest body, omitting unset optional fields."""
    body: dict[str, Any] = {"activity": p.activity, "params": p.params or {}}
    for key in ("label", "save_token_as", "scope", "audience", "endpoint", "user_agent"):
        val = getattr(p, key)
        if val is not None:
            body[key] = val
    if p.use_beta:
        body["use_beta"] = True
    if p.check_privileges:
        body["check_privileges"] = True
    return body


# --------------------------------------------------------------------------- #
# Pydantic input models
# --------------------------------------------------------------------------- #
_strict = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Empty(BaseModel):
    model_config = _strict


class AssessmentId(BaseModel):
    model_config = _strict
    assessment_id: int = Field(..., description="Assessment id.", ge=1)


class JobId(BaseModel):
    model_config = _strict
    job_id: int = Field(..., description="Job id.", ge=1)


class ListAssessmentsInput(BaseModel):
    model_config = _strict
    status: Optional[str] = Field(None, description="Filter by status, e.g. 'active' or 'archived'.")


class CreateAssessmentInput(BaseModel):
    model_config = _strict
    name: str = Field(..., description="Engagement name.", min_length=1, max_length=200)
    client: Optional[str] = Field(None, description="Client / organisation name.", max_length=200)
    description: Optional[str] = Field(None, description="Free-text description.")
    scope_notes: Optional[str] = Field(None, description="Authorised scope notes.")


class UpdateAssessmentInput(BaseModel):
    model_config = _strict
    assessment_id: int = Field(..., description="Assessment id.", ge=1)
    name: Optional[str] = Field(None, max_length=200)
    client: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    scope_notes: Optional[str] = None
    status: Optional[str] = Field(None, description="e.g. 'active' or 'archived'.")


class AddVaultTokenInput(BaseModel):
    model_config = _strict
    assessment_id: int = Field(..., description="Owning assessment id.", ge=1)
    name: str = Field(..., description="Label for the stored token.", min_length=1, max_length=200)
    access_token: str = Field(..., description="Raw access token (JWT). Claims are auto-extracted.")
    refresh_token: Optional[str] = Field(None, description="Raw refresh token, if available.")
    tenant_id: Optional[str] = Field(None, description="Overrides the JWT 'tid' claim.")
    username: Optional[str] = Field(None, description="Overrides the JWT 'upn'/'unique_name' claim.")


class VaultTokenRef(BaseModel):
    model_config = _strict
    assessment_id: int = Field(..., description="Owning assessment id.", ge=1)
    token_id: int = Field(..., description="Vault token id.", ge=1)


class ListJobsInput(BaseModel):
    model_config = _strict
    assessment_id: int = Field(..., description="Assessment id.", ge=1)
    activity: Optional[str] = Field(None, description="Filter by activity key, e.g. 'spray'.")


class JobLogsInput(BaseModel):
    model_config = _strict
    job_id: int = Field(..., description="Job id.", ge=1)
    after: int = Field(0, description="Return only log lines with id greater than this.", ge=0)


class WaitForJobInput(BaseModel):
    model_config = _strict
    job_id: int = Field(..., description="Job id to wait on.", ge=1)
    timeout_seconds: int = Field(120, description="Max seconds to wait for a terminal status.", ge=1, le=1800)
    poll_interval_seconds: float = Field(2.0, description="Seconds between polls.", ge=0.5, le=30)


class RunOperationInput(BaseModel):
    """Run an AzureRedOps operation (activity) as an async backend job.

    Discover valid `activity` values and the `params` each one needs via
    `redops_get_catalog`. Token-backed activities accept either a vault
    `token_id` or a raw `access_token` inside `params`.
    """
    model_config = _strict
    assessment_id: int = Field(..., description="Assessment that will own the job.", ge=1)
    activity: str = Field(..., description="Operation key, e.g. 'id','self','spray','auth','gather-all'.", min_length=1)
    params: dict[str, Any] = Field(default_factory=dict, description="Activity-specific params (see redops_get_catalog).")
    label: Optional[str] = Field(None, description="Human label for the job (defaults to the activity).")
    save_token_as: Optional[str] = Field(None, description="For token-producing activities, auto-store the result in the vault under this name.")
    check_privileges: bool = Field(False, description="On successful auth, probe for privileges.")
    use_beta: bool = Field(False, description="Use the Microsoft Graph beta endpoint.")
    scope: Optional[str] = Field(None, description="Override the OAuth scope.")
    audience: Optional[str] = Field(None, description="Override the token audience.")
    endpoint: Optional[str] = Field(None, description="Override the Microsoft endpoint host.")
    user_agent: Optional[str] = Field(None, description="Override the outbound User-Agent.")


class RunAndWaitInput(RunOperationInput):
    timeout_seconds: int = Field(180, description="Max seconds to wait for the job to finish.", ge=1, le=1800)
    poll_interval_seconds: float = Field(2.0, description="Seconds between polls.", ge=0.5, le=30)


class KnownIdsInput(BaseModel):
    model_config = _strict
    search: Optional[str] = Field(None, description="Case-insensitive substring filter over name/appId.")
    limit: int = Field(100, description="Max results to return.", ge=1, le=1000)
    offset: int = Field(0, description="Results to skip (pagination).", ge=0)


class InterestInput(BaseModel):
    model_config = _strict
    category: Optional[str] = Field(None, description="Restrict to a single interest category.")


# --------------------------------------------------------------------------- #
# Tools — connectivity
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_health",
    annotations={"title": "Backend health", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_health(params: Empty) -> str:
    """Check that the AzureRedOps backend is reachable and healthy.

    Returns: JSON `{"status": "ok", "service": "azureredops-console"}` on success,
    or an `Error: ...` string if the backend cannot be reached.
    """
    try:
        return _dump(await _api("GET", "/api/health"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_whoami",
    annotations={"title": "Current backend user", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_whoami(params: Empty) -> str:
    """Return the backend principal the MCP server is authenticated as.

    Returns: JSON `{"username": str, "is_admin": bool}`. Useful to confirm the
    MCP server's admin credentials are valid before running operations.
    """
    try:
        return _dump(await _api("GET", "/api/auth/me"))
    except Exception as e:
        return _err(e)


# --------------------------------------------------------------------------- #
# Tools — assessments
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_list_assessments",
    annotations={"title": "List assessments", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_list_assessments(params: ListAssessmentsInput) -> str:
    """List engagement assessments, optionally filtered by status.

    Args: status (Optional[str]) — e.g. 'active' or 'archived'.
    Returns: JSON array of AssessmentOut objects (id, name, client, status,
    token_count, job_count, created_at, updated_at, ...).
    """
    try:
        q = {"status": params.status} if params.status else None
        return _dump(await _api("GET", "/api/assessments", params=q))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_get_assessment",
    annotations={"title": "Get assessment", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_get_assessment(params: AssessmentId) -> str:
    """Get a single assessment by id. Returns an AssessmentOut JSON object."""
    try:
        return _dump(await _api("GET", f"/api/assessments/{params.assessment_id}"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_create_assessment",
    annotations={"title": "Create assessment", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
async def redops_create_assessment(params: CreateAssessmentInput) -> str:
    """Create a new engagement assessment (the container for tokens and jobs).

    Args: name (required), client, description, scope_notes (all optional).
    Returns: the created AssessmentOut JSON (including its new `id`).
    """
    try:
        body = params.model_dump(exclude_none=True)
        return _dump(await _api("POST", "/api/assessments", json=body))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_update_assessment",
    annotations={"title": "Update assessment", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
async def redops_update_assessment(params: UpdateAssessmentInput) -> str:
    """Partially update an assessment. Only supplied fields are changed.

    Args: assessment_id (required); any of name, client, description, scope_notes, status.
    Returns: the updated AssessmentOut JSON.
    """
    try:
        body = params.model_dump(exclude_none=True, exclude={"assessment_id"})
        return _dump(await _api("PATCH", f"/api/assessments/{params.assessment_id}", json=body))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_archive_assessment",
    annotations={"title": "Archive assessment", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_archive_assessment(params: AssessmentId) -> str:
    """Archive an assessment (sets status='archived'). Returns the AssessmentOut JSON."""
    try:
        return _dump(await _api("POST", f"/api/assessments/{params.assessment_id}/archive"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_restore_assessment",
    annotations={"title": "Restore assessment", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_restore_assessment(params: AssessmentId) -> str:
    """Restore an archived assessment (sets status='active'). Returns the AssessmentOut JSON."""
    try:
        return _dump(await _api("POST", f"/api/assessments/{params.assessment_id}/restore"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_delete_assessment",
    annotations={"title": "Delete assessment", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_delete_assessment(params: AssessmentId) -> str:
    """Permanently delete an assessment AND all its vault tokens and jobs (cascade).

    Destructive and irreversible. Returns a confirmation string on success.
    """
    try:
        await _api("DELETE", f"/api/assessments/{params.assessment_id}")
        return f"Deleted assessment {params.assessment_id} (and its tokens and jobs)."
    except Exception as e:
        return _err(e)


# --------------------------------------------------------------------------- #
# Tools — token vault
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_list_vault_tokens",
    annotations={"title": "List vault tokens", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_list_vault_tokens(params: AssessmentId) -> str:
    """List the stored tokens for an assessment (metadata only; never the raw token).

    Returns: JSON array of TokenOut objects (id, name, tenant_id, username, scope,
    audience, expires, expires_human, is_expired, created_at).
    """
    try:
        return _dump(await _api("GET", f"/api/assessments/{params.assessment_id}/tokens"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_add_vault_token",
    annotations={"title": "Add vault token", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
async def redops_add_vault_token(params: AddVaultTokenInput) -> str:
    """Store a captured access/refresh token in an assessment's encrypted vault.

    JWT claims (tid, upn, scp, aud, exp) are auto-extracted from access_token.
    Args: assessment_id, name, access_token (required); refresh_token, tenant_id, username (optional).
    Returns: the created TokenOut JSON (metadata, no raw token).
    """
    try:
        body = params.model_dump(exclude_none=True, exclude={"assessment_id"})
        return _dump(await _api("POST", f"/api/assessments/{params.assessment_id}/tokens", json=body))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_reveal_vault_token",
    annotations={"title": "Reveal vault token", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_reveal_vault_token(params: VaultTokenRef) -> str:
    """Decrypt and return a stored token's raw value and decoded claims. SENSITIVE.

    Args: assessment_id, token_id.
    Returns: JSON `{"access_token": str, "refresh_token": str|null, "claims": {...}}`.
    """
    try:
        return _dump(await _api(
            "GET", f"/api/assessments/{params.assessment_id}/tokens/{params.token_id}/reveal"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_delete_vault_token",
    annotations={"title": "Delete vault token", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_delete_vault_token(params: VaultTokenRef) -> str:
    """Permanently delete a stored token from an assessment's vault.

    Args: assessment_id, token_id. Returns a confirmation string.
    """
    try:
        await _api("DELETE", f"/api/assessments/{params.assessment_id}/tokens/{params.token_id}")
        return f"Deleted vault token {params.token_id} from assessment {params.assessment_id}."
    except Exception as e:
        return _err(e)


# --------------------------------------------------------------------------- #
# Tools — catalog & operations
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_get_catalog",
    annotations={"title": "Operation catalog", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_get_catalog(params: Empty) -> str:
    """Return the full operation catalog: every runnable activity and its parameters.

    Use this FIRST to discover valid `activity` values and the `params` keys each
    one expects before calling redops_run_operation / redops_run_operation_and_wait.

    Returns: JSON array of groups, each `{key, title, operations: [{activity, name,
    long_running, description, fields: [{name, label, type, required, ...}]}]}`.
    """
    try:
        return _dump(await _api("GET", "/api/catalog"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_run_operation",
    annotations={"title": "Run operation (async)", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": True},
)
async def redops_run_operation(params: RunOperationInput) -> str:
    """Submit an AzureRedOps operation as an asynchronous backend job and return immediately.

    The job runs in a backend worker; this returns the created Job (status 'pending'/
    'running'). Use redops_wait_for_job / redops_get_job / redops_get_job_logs to follow
    it, or prefer redops_run_operation_and_wait to submit and block in one call.

    NOTE: operations perform LIVE actions against Azure/Entra ID (auth, password spraying,
    Graph reads/writes). Many are destructive. Run only against authorised tenants.

    Args:
        assessment_id (int): assessment that owns the job.
        activity (str): operation key — see redops_get_catalog.
        params (dict): activity-specific parameters — see redops_get_catalog.
        label, save_token_as, check_privileges, use_beta, scope, audience, endpoint,
        user_agent: optional, mirror the OperationRequest fields.

    Returns: JSON JobOut `{id, assessment_id, activity, label, status, params, result,
    error, created_at, started_at, finished_at}`.
    """
    try:
        body = _operation_body(params)
        return _dump(await _api(
            "POST", f"/api/assessments/{params.assessment_id}/operations", json=body))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_run_operation_and_wait",
    annotations={"title": "Run operation and wait", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": True},
)
async def redops_run_operation_and_wait(params: RunAndWaitInput) -> str:
    """Submit an operation AND wait for it to finish, returning the result and logs.

    Convenience workflow tool: submits the job, then polls until it reaches a terminal
    status (completed/failed/cancelled) or the timeout elapses. Same LIVE-action and
    authorisation caveats as redops_run_operation apply.

    Args: as redops_run_operation, plus timeout_seconds (default 180) and
    poll_interval_seconds (default 2.0).

    Returns: JSON `{"job": JobOut, "logs": [JobLogOut...], "timed_out": bool}`. If
    timed_out is true the job may still be running — follow up with redops_wait_for_job.
    """
    try:
        body = _operation_body(params)
        job = await _api("POST", f"/api/assessments/{params.assessment_id}/operations", json=body)
        result = await _poll_job(job["id"], params.timeout_seconds, params.poll_interval_seconds)
        return _dump(result)
    except Exception as e:
        return _err(e)


# --------------------------------------------------------------------------- #
# Tools — jobs
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_list_jobs",
    annotations={"title": "List jobs", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_list_jobs(params: ListJobsInput) -> str:
    """List jobs for an assessment (newest first), optionally filtered by activity.

    Returns: JSON array of JobSummary `{id, assessment_id, activity, label, status,
    created_at, finished_at}`.
    """
    try:
        q = {"activity": params.activity} if params.activity else None
        return _dump(await _api("GET", f"/api/assessments/{params.assessment_id}/jobs", params=q))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_get_job",
    annotations={"title": "Get job", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_get_job(params: JobId) -> str:
    """Get full detail for one job, including its JSON `result` and `error`.

    Returns: JobOut JSON. `status` is pending|running|completed|failed|cancelled.
    """
    try:
        return _dump(await _api("GET", f"/api/jobs/{params.job_id}"))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_get_job_logs",
    annotations={"title": "Get job logs", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_get_job_logs(params: JobLogsInput) -> str:
    """Get a job's log lines, optionally only those after a given log id (for polling).

    Args: job_id; after (int, default 0) — return only lines with id > after.
    Returns: JSON array of JobLogOut `{id, ts, level, message}`.
    """
    try:
        return _dump(await _api("GET", f"/api/jobs/{params.job_id}/logs",
                                params={"after": params.after}))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_wait_for_job",
    annotations={"title": "Wait for job", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_wait_for_job(params: WaitForJobInput) -> str:
    """Poll an existing job until it reaches a terminal status or the timeout elapses.

    Args: job_id; timeout_seconds (default 120); poll_interval_seconds (default 2.0).
    Returns: JSON `{"job": JobOut, "logs": [JobLogOut...], "timed_out": bool}`.
    """
    try:
        result = await _poll_job(params.job_id, params.timeout_seconds, params.poll_interval_seconds)
        return _dump(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_cancel_job",
    annotations={"title": "Cancel job", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_cancel_job(params: JobId) -> str:
    """Request cancellation of a running job (long-running activities only).

    Returns: JSON `{"cancelled": bool, "status": str}`. The job transitions to
    'cancelled' at its next cancellation checkpoint.
    """
    try:
        return _dump(await _api("POST", f"/api/jobs/{params.job_id}/cancel"))
    except Exception as e:
        return _err(e)


async def _poll_job(job_id: int, timeout_seconds: int, poll_interval: float) -> dict:
    """Poll a job + accumulate its logs until terminal or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_seconds
    last_log_id = 0
    logs: list[dict] = []
    while True:
        job = await _api("GET", f"/api/jobs/{job_id}")
        new_logs = await _api("GET", f"/api/jobs/{job_id}/logs", params={"after": last_log_id})
        if new_logs:
            logs.extend(new_logs)
            last_log_id = new_logs[-1]["id"]
        if job.get("status") in TERMINAL_STATUSES:
            return {"job": job, "logs": logs, "timed_out": False}
        if loop.time() >= deadline:
            return {"job": job, "logs": logs, "timed_out": True}
        await asyncio.sleep(poll_interval)


# --------------------------------------------------------------------------- #
# Tools — reference data
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="redops_reference_known_ids",
    annotations={"title": "Known app IDs", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_reference_known_ids(params: KnownIdsInput) -> str:
    """Look up well-known first-party Microsoft application IDs (paginated, searchable).

    Args: search (optional substring), limit (default 100), offset (default 0).
    Returns: JSON `{"total": int, "items": [{"name": str, "appId": str}]}`.
    """
    try:
        q: dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        if params.search:
            q["search"] = params.search
        return _dump(await _api("GET", "/api/reference/known-ids", params=q))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="redops_reference_interest",
    annotations={"title": "Objects of interest", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def redops_reference_interest(params: InterestInput) -> str:
    """List bundled "objects of interest" reference entries, optionally by category.

    With no category, also returns the available categories. Args: category (optional).
    Returns: JSON — the interest entries (and categories when unfiltered).
    """
    try:
        if params.category:
            entries = await _api("GET", "/api/reference/interest",
                                 params={"category": params.category})
            return _dump({"category": params.category, "entries": entries})
        categories = await _api("GET", "/api/reference/interest/categories")
        entries = await _api("GET", "/api/reference/interest")
        return _dump({"categories": categories, "entries": entries})
    except Exception as e:
        return _err(e)


# --------------------------------------------------------------------------- #
# Transport: Streamable HTTP + bearer-token auth middleware
# --------------------------------------------------------------------------- #
class BearerAuthMiddleware:
    """Pure-ASGI middleware: require `Authorization: Bearer <MCP_API_KEY>` on HTTP requests.

    Forwards non-HTTP scopes (e.g. the ASGI 'lifespan' events) untouched so the MCP
    session manager still starts/stops correctly. A no-op if MCP_API_KEY is unset.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token
        self._expected = f"Bearer {token}".encode() if token else b""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"")
        if not hmac.compare_digest(provided, self._expected):
            body = b'{"error":"unauthorized","detail":"missing or invalid bearer token"}'
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


# Hosts/origins permitted by the transport's DNS-rebinding protection by default.
# The SDK already allows these, which covers connecting from this machine to
# 127.0.0.1:<MCP_PORT>. We keep protection ON and only extend the lists on request.
_LOCALHOST_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCALHOST_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _configure_security() -> None:
    """Configure the transport's Host/Origin (DNS-rebinding) protection.

    Default: keep the SDK's localhost-only allow-list (works for 127.0.0.1/localhost
    access). Set MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS (comma-separated) to also allow
    other hosts — e.g. `mcp:9000` for an in-cluster client. Set MCP_DISABLE_HOST_CHECK=1
    to turn the check off entirely (only sensible behind a trusted proxy / bearer token).
    """
    try:
        from mcp.server.transport_security import TransportSecuritySettings
    except Exception:
        return  # very old SDK without configurable transport security; defaults apply

    if os.environ.get("MCP_DISABLE_HOST_CHECK", "").lower() in ("1", "true", "yes"):
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False)
        return

    extra_hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    extra_origins = [o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if extra_hosts or extra_origins:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_LOCALHOST_HOSTS + extra_hosts,
            allowed_origins=_LOCALHOST_ORIGINS + extra_origins,
        )
    # else: leave the SDK defaults (localhost-only), which already permit our binding.


def build_app():
    if not MCP_API_KEY:
        print("WARNING: MCP_API_KEY is not set — the MCP server is UNAUTHENTICATED. "
              "Set MCP_API_KEY before exposing it.", file=sys.stderr)
    _configure_security()
    return BearerAuthMiddleware(mcp.streamable_http_app(), MCP_API_KEY)


# Exposed for `uvicorn server:app` deployments.
app = build_app()


if __name__ == "__main__":
    import uvicorn
    print(f"AzureRedOps MCP server -> backend {BACKEND_URL}; "
          f"listening on http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}", file=sys.stderr)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
