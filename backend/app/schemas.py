import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ----- auth ----------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ----- assessments ---------------------------------------------------------
class AssessmentCreate(BaseModel):
    name: str
    client: Optional[str] = None
    description: Optional[str] = None
    scope_notes: Optional[str] = None


class AssessmentUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    description: Optional[str] = None
    scope_notes: Optional[str] = None
    status: Optional[str] = None


class AssessmentOut(BaseModel):
    id: int
    name: str
    client: Optional[str]
    description: Optional[str]
    scope_notes: Optional[str]
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    token_count: int = 0
    job_count: int = 0

    class Config:
        from_attributes = True


# ----- tokens (vault) ------------------------------------------------------
class TokenCreate(BaseModel):
    name: str
    access_token: str
    refresh_token: Optional[str] = None
    tenant_id: Optional[str] = None
    username: Optional[str] = None


class TokenOut(BaseModel):
    id: int
    assessment_id: int
    name: str
    tenant_id: Optional[str]
    username: Optional[str]
    scope: Optional[str]
    audience: Optional[str]
    expires: Optional[int]
    expires_human: Optional[str] = None
    is_expired: Optional[bool] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TokenReveal(BaseModel):
    access_token: str
    refresh_token: Optional[str]
    claims: dict


# ----- jobs / operations ---------------------------------------------------
class OperationRequest(BaseModel):
    activity: str
    params: dict[str, Any] = {}
    label: Optional[str] = None
    # optional global request options mirrored from the CLI flags
    endpoint: Optional[str] = None
    user_agent: Optional[str] = None
    audience: Optional[str] = None
    scope: Optional[str] = None
    use_beta: bool = False
    additional_headers: Optional[dict[str, str]] = None
    filters: Optional[list[str]] = None
    check_privileges: bool = False
    save_token_as: Optional[str] = None  # auto-store resulting token in vault


class JobLogOut(BaseModel):
    id: int
    ts: datetime.datetime
    level: str
    message: str

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: int
    assessment_id: int
    activity: str
    label: Optional[str]
    status: str
    params: Optional[dict]
    result: Optional[Any]
    error: Optional[str]
    created_at: datetime.datetime
    started_at: Optional[datetime.datetime]
    finished_at: Optional[datetime.datetime]

    class Config:
        from_attributes = True


class JobSummary(BaseModel):
    id: int
    assessment_id: int
    activity: str
    label: Optional[str]
    status: str
    created_at: datetime.datetime
    finished_at: Optional[datetime.datetime]

    class Config:
        from_attributes = True
