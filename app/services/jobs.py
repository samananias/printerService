"""
Job tracking (Phase 7) — in-memory store, exactly as SOURCE_OF_TRUTH
Section 12 prescribes for v1: a Python dict, no database.

Known trade-off (accepted for v1): job history disappears if the service
restarts. If that ever hurts, the Section 12 upgrade path is JSON file →
SQLite.

Why the lock: Uvicorn runs sync endpoint functions in a small thread pool,
so two simultaneous requests could mutate the dict at once. A threading.Lock
makes "check then modify" sequences safe — the simplest correct tool here.
"""

import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.printing import JobStatus, PrintJob

_lock = threading.Lock()
_jobs: dict[str, PrintJob] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(job_id: str, filename: str, size_bytes: int, path: Path) -> PrintJob:
    """Register a freshly uploaded file as a tracked job."""
    job = PrintJob(
        job_id=job_id,
        filename=filename,
        size_bytes=size_bytes,
        status=JobStatus.RECEIVED,
        created_at=_now(),
        updated_at=_now(),
    )
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> PrintJob | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[PrintJob]:
    """All jobs, oldest first (dicts preserve insertion order)."""
    with _lock:
        return list(_jobs.values())


def update_status(
    job_id: str,
    status: str,
    error: str | None = None,
    printer: str | None = None,
) -> None:
    """Move a job along its lifecycle (used by Phase 5's printing code).

    error/printer are only written when provided; reaching 'done' clears a
    stale error, since the job obviously succeeded.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job.status = status
            if error is not None:
                job.error = error
            elif status == JobStatus.DONE:
                job.error = None
            if printer is not None:
                job.printer = printer
            job.updated_at = _now()


def cancel_job(job_id: str) -> tuple[bool, str]:
    """Cancel a job that hasn't reached the Windows print queue yet.

    Returns (ok, message). Only 'received' jobs are cancellable in Phase 7 —
    once Phase 5 submits a job to the spooler, cancellation has to go
    through Windows (win32print.SetJob), which is Phase 5/P8 territory.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False, "No such job."
        if job.status != JobStatus.RECEIVED:
            return False, (
                f"Job is '{job.status}' — only jobs that haven't been handed "
                "to the print queue can be cancelled."
            )
        job.status = JobStatus.CANCELLED
        job.updated_at = _now()
    return True, "Cancelled."
