from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from .. import models, schemas

router = APIRouter(prefix="/api/assessments", tags=["assessments"],
                   dependencies=[Depends(get_current_user)])


def _to_out(a: models.Assessment) -> schemas.AssessmentOut:
    out = schemas.AssessmentOut.model_validate(a)
    out.token_count = len(a.tokens)
    out.job_count = len(a.jobs)
    return out


@router.get("", response_model=list[schemas.AssessmentOut])
def list_assessments(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Assessment)
    if status:
        query = query.filter(models.Assessment.status == status)
    items = query.order_by(models.Assessment.updated_at.desc()).all()
    return [_to_out(a) for a in items]


@router.post("", response_model=schemas.AssessmentOut, status_code=201)
def create_assessment(payload: schemas.AssessmentCreate, db: Session = Depends(get_db)):
    assessment = models.Assessment(**payload.model_dump())
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return _to_out(assessment)


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    return _to_out(assessment)


@router.patch("/{assessment_id}", response_model=schemas.AssessmentOut)
def update_assessment(assessment_id: int, payload: schemas.AssessmentUpdate,
                      db: Session = Depends(get_db)):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(assessment, key, value)
    db.commit()
    db.refresh(assessment)
    return _to_out(assessment)


@router.post("/{assessment_id}/archive", response_model=schemas.AssessmentOut)
def archive_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    assessment.status = "archived"
    db.commit()
    db.refresh(assessment)
    return _to_out(assessment)


@router.post("/{assessment_id}/restore", response_model=schemas.AssessmentOut)
def restore_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    assessment.status = "active"
    db.commit()
    db.refresh(assessment)
    return _to_out(assessment)


@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(models.Assessment).get(assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    db.delete(assessment)
    db.commit()
