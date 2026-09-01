"""
Jobs API (Phase 7; queue management in p14) — see what happened, poll
status, cancel mistakes, retry failures.

Endpoints (SOURCE_OF_TRUTH Section 11, extended by p14):
  GET    /jobs              — recent jobs and their statuses
  GET    /jobs/{id}         — one job (what the phone UI polls: "done yet?")
  DELETE /jobs/{id}         — cancel a job (queued/converting/printing)
  POST   /jobs/{id}/retry   — re-print a failed job from its stored upload
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.models.printing import JobStatus, PrintJob
from app.printer import windows
from app.services import jobs, pipeline, uploads
from app.services.auth import require_pin

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/jobs", response_model=list[PrintJob])
def all_jobs():
    """Recent jobs and statuses, oldest first."""
    return jobs.list_jobs()


@router.get("/jobs/{job_id}", response_model=PrintJob)
def one_job(job_id: str):
    """Status of one job — the endpoint a phone UI polls after uploading."""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id '{job_id}'.")
    return job


@router.delete("/jobs/{job_id}", response_model=PrintJob)
def cancel(job_id: str, _: None = Depends(require_pin)):
    """Cancel a job (Section 11: "you will queue the wrong file").

    p14: cancellation works while queued, converting AND printing. The
    printing case is best-effort — our queued spooler jobs are purged via
    win32print, but paper that already fed into the printer cannot be
    recalled; the pipeline never marks a cancelled job done.
    """
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id '{job_id}'.")
    was_printing = job.status == JobStatus.PRINTING

    ok, message = jobs.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)

    # Best-effort spooler purge for anything already handed to Windows.
    # Never fails the cancel — a purge hiccup must not 500 the request.
    if was_printing:
        try:
            removed = windows.cancel_spooler_jobs(
                windows.resolve_printer_name(), job_id
            )
            if removed:
                logger.info(
                    "purged %d spooler job(s) for cancelled job %s", removed, job_id
                )
        except Exception:
            logger.warning(
                "spooler purge failed for cancelled job %s", job_id, exc_info=True
            )

    # Remove the stored file(s) so cancelled uploads don't fill the disk.
    # delete_job_files covers the source upload and its converted PDF.
    uploads.delete_job_files(job_id)

    return jobs.get_job(job_id)


@router.post("/jobs/{job_id}/retry", response_model=PrintJob)
def retry(job_id: str, _: None = Depends(require_pin)):
    """Re-print a failed job (p14).

    Failed jobs keep their uploaded file precisely for this. The pipeline
    re-runs from conversion — a transient failure (printer offline, a
    LibreOffice hiccup) becomes a second chance without re-uploading.
    """
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id '{job_id}'.")
    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.status}' — only failed jobs can be retried.",
        )

    source = jobs.get_source(job_id)
    if source is None or not source[0].is_file():
        raise HTTPException(
            status_code=409,
            detail="The uploaded file for this job is gone — upload it again.",
        )

    jobs.reset_for_retry(job_id)
    pipeline.start_job(job_id, source[0], source[1], options=job.options)
    logger.info("job %s queued for retry", job_id)
    return jobs.get_job(job_id)
