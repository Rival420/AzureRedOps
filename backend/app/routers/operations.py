from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..catalog import CATALOG
from ..jobs import manager
from .. import models, schemas

router = APIRouter(prefix="/api", tags=["operations"],
                   dependencies=[Depends(get_current_user)])


@router.get("/catalog")
def get_catalog():
    return CATALOG


@router.post("/assessments/{assessment_id}/operations", response_model=schemas.JobOut,
             status_code=202)
def run_operation(assessment_id: int, payload: schemas.OperationRequest,
                  db: Session = Depends(get_db)):
    if not db.query(models.Assessment).get(assessment_id):
        raise HTTPException(404, "Assessment not found")

    job = models.Job(
        assessment_id=assessment_id,
        activity=payload.activity,
        label=payload.label or payload.activity,
        status="pending",
        params=payload.params,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    options = {
        "endpoint": payload.endpoint,
        "user_agent": payload.user_agent,
        "audience": payload.audience,
        "scope": payload.scope,
        "use_beta": payload.use_beta,
        "additional_headers": payload.additional_headers,
        "filters": payload.filters,
        "check_privileges": payload.check_privileges,
        "save_token_as": payload.save_token_as,
    }
    manager.submit(job.id, options)
    return job
