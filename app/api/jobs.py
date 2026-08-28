"""
Jobs API (Phase 7) — see what happened, poll status, cancel mistakes.

Endpoints (SOURCE_OF_TRUTH Section 11):
  GET    /jobs        — recent jobs and their statuses
  GET    /jobs/{id}   — one job (what the phone UI polls: "done yet?")
  DELETE /jobs/{id}   — cancel a job that hasn't reached the print queue
"""

from fastapi import APIRouter, Depends, HTTPException

from app.models.printing import PrintJob
from app.services import jobs, uploads
from app.services.auth import require_pin

router = APIRouter()


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
    """Cancel a queued job (Section 11: "you will queue the wrong file")."""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job with id '{job_id}'.")

    ok, message = jobs.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)

    # Remove the stored file(s) so cancelled uploads don't fill the disk.
    # delete_job_files covers the source upload and, once non-PDF formats
    # land, its converted PDF alongside it.
    uploads.delete_job_files(job_id)

    return jobs.get_job(job_id)
