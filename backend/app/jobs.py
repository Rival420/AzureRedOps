"""Background job execution: runs activities in worker threads, persists logs."""

import threading
import datetime
from concurrent.futures import ThreadPoolExecutor

from .database import SessionLocal
from . import models, runner
from .core.redops import RedOpsService, RedOpsError, CancelledError


class JobManager:
    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cancel_events: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: int, options: dict):
        cancel_event = threading.Event()
        with self._lock:
            self.cancel_events[job_id] = cancel_event
        self.executor.submit(self._run, job_id, options, cancel_event)

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            event = self.cancel_events.get(job_id)
        if event:
            event.set()
            return True
        return False

    def _run(self, job_id: int, options: dict, cancel_event: threading.Event):
        db = SessionLocal()
        try:
            job = db.query(models.Job).get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = datetime.datetime.utcnow()
            db.commit()

            def emit(message: str, level: str = "info"):
                entry = models.JobLog(job_id=job_id, level=level, message=str(message))
                db.add(entry)
                db.commit()

            service = RedOpsService(
                emit=emit,
                should_cancel=cancel_event.is_set,
                endpoint=options.get("endpoint"),
                user_agent=options.get("user_agent"),
                audience=options.get("audience"),
                scope=options.get("scope"),
                use_beta=options.get("use_beta", False),
                additional_headers=options.get("additional_headers"),
                filters=options.get("filters"),
            )

            try:
                params = dict(job.params or {})
                params.setdefault("check_privileges", options.get("check_privileges", False))
                result = runner.execute(job.activity, params, service, db, job)
                job.result = _jsonable(result)
                job.status = "completed"
                emit("Job completed.", "success")
                self._maybe_store_token(db, job, result, options)
            except CancelledError:
                job.status = "cancelled"
                emit("Job cancelled.", "warning")
            except RedOpsError as exc:
                job.status = "failed"
                job.error = str(exc)
                emit(f"Error: {exc}", "error")
            except Exception as exc:  # pragma: no cover - defensive
                job.status = "failed"
                job.error = repr(exc)
                emit(f"Unexpected error: {exc!r}", "error")

            job.finished_at = datetime.datetime.utcnow()
            db.commit()
        finally:
            db.close()
            with self._lock:
                self.cancel_events.pop(job_id, None)

    def _maybe_store_token(self, db, job, result, options):
        save_as = options.get("save_token_as")
        if not save_as or job.activity not in runner.TOKEN_PRODUCING:
            return
        if isinstance(result, dict) and result.get("access_token"):
            runner.store_token_in_vault(db, job.assessment_id, save_as, result)
            db.add(models.JobLog(job_id=job.id, level="success",
                                 message=f"Token saved to vault as '{save_as}'."))
            db.commit()


def _jsonable(value):
    """Best-effort conversion of results into JSON-serialisable structures."""
    import json
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


manager = JobManager()
