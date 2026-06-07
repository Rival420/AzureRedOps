import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..deps import get_current_user
from ..jobs import manager
from .. import models, schemas

router = APIRouter(prefix="/api", tags=["jobs"],
                   dependencies=[Depends(get_current_user)])

TERMINAL = {"completed", "failed", "cancelled"}


@router.get("/assessments/{assessment_id}/jobs", response_model=list[schemas.JobSummary])
def list_jobs(assessment_id: int, activity: str | None = None,
              db: Session = Depends(get_db)):
    query = db.query(models.Job).filter(models.Job.assessment_id == assessment_id)
    if activity:
        query = query.filter(models.Job.activity == activity)
    return query.order_by(models.Job.created_at.desc()).all()


@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/logs", response_model=list[schemas.JobLogOut])
def get_logs(job_id: int, after: int = 0, db: Session = Depends(get_db)):
    return (db.query(models.JobLog)
            .filter(models.JobLog.job_id == job_id, models.JobLog.id > after)
            .order_by(models.JobLog.id).all())


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    cancelled = manager.cancel(job_id)
    return {"cancelled": cancelled, "status": job.status}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int, request: Request, after: int = 0):
    """Server-sent events: live log lines followed by a terminal status event."""

    def read_new(last_id: int):
        db = SessionLocal()
        try:
            job = db.query(models.Job).get(job_id)
            if not job:
                return None, [], last_id
            logs = (db.query(models.JobLog)
                    .filter(models.JobLog.job_id == job_id, models.JobLog.id > last_id)
                    .order_by(models.JobLog.id).all())
            payload = [{"id": l.id, "ts": l.ts.isoformat(), "level": l.level,
                        "message": l.message} for l in logs]
            new_last = logs[-1].id if logs else last_id
            return job.status, payload, new_last
        finally:
            db.close()

    async def event_gen():
        last_id = after
        while True:
            if await request.is_disconnected():
                break
            status, logs, last_id = await asyncio.to_thread(read_new, last_id)
            if status is None:
                yield f"event: error\ndata: {json.dumps({'message': 'job not found'})}\n\n"
                break
            for entry in logs:
                yield f"event: log\ndata: {json.dumps(entry)}\n\n"
            if status in TERMINAL:
                yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
                break
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
