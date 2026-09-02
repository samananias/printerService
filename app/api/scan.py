"""Scan API (docs/SCAN_PLAN.md §4) — Phase 2: the basic scan pipeline.

    POST /scan                     — start a scan: 201 + job id; 503 when
                                     disabled or scanner-less (an expected,
                                     documented state, not a 500)
    GET  /scan/jobs/{id}           — poll status; carries the download link
                                     once done
    GET  /scan/jobs/{id}/download  — the finished PDF
    DELETE /scan/jobs/{id}         — cancel + cleanup (queued or scanning)

Same shape as the print surface (server-generated job id, accept
immediately, poll) but its own namespace: a scan is not a print job in
either direction (SCAN_PLAN §4). PIN applies to the state-changing routes
only — read-only GETs stay open (app/services/auth.py convention).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse

from app.models.scanning import (
    DEFAULT_DPI,
    SCAN_FILE_EXT,
    ScanAccepted,
    ScanJob,
    ScanStatus,
    validate_scan_options,
)
from app.scanner.windows import ENABLE_SCAN, scanning_supported
from app.services import downloads, scan_jobs
from app.services.auth import require_pin
from app.services.scan_pipeline import start_scan

router = APIRouter()
logger = logging.getLogger(__name__)


def _gate() -> None:
    """The two gates ANDed (SCAN_PLAN §3.4), refused with a clear 503."""
    if not ENABLE_SCAN:
        raise HTTPException(
            status_code=503,
            detail="Scanning is disabled on this server (ENABLE_SCAN=0).",
        )
    if not scanning_supported():
        raise HTTPException(
            status_code=503,
            detail=(
                "No scanner detected on this server — check that the printer "
                "is powered on and the USB cable is seated."
            ),
        )


@router.post("/scan", response_model=ScanAccepted, status_code=201)
def start_scan_job(
    dpi: int = Form(DEFAULT_DPI),
    color_mode: str = Form("color"),
    format: str = Form("pdf"),
    _: None = Depends(require_pin),
):
    """Start a flatbed scan (Phase 4: dpi / color_mode / format options).

    All options are optional with safe defaults and strictly allowlisted —
    validated BEFORE anything touches WIA, the same rule the print side
    applies to its command-line-bound options (Phase 7). Accepts
    immediately — the transfer takes tens of seconds (spike S2 measured
    41 s at 200 dpi) — and hands the job to the background pipeline. Poll
    GET /scan/jobs/{id} until it carries a download link.
    """
    _gate()
    try:
        options = validate_scan_options(dpi, color_mode, format).model_dump()
    except ValueError as exc:
        logger.warning("rejected scan request: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    job_id = uuid.uuid4().hex
    job = scan_jobs.create_job(job_id, options)
    logger.info("scan job %s accepted (%s)", job_id, options)
    start_scan(job_id, options)
    return ScanAccepted(job_id=job.job_id, status=job.status)


@router.get("/scan/jobs/{job_id}", response_model=ScanJob)
def scan_job_status(job_id: str):
    """Poll a scan — the phone's "is my scan done yet?" endpoint. The
    response carries download_url once the scan is done."""
    job = _get_job_or_404(job_id)
    if job.status == ScanStatus.DONE:
        job.download_url = f"/scan/jobs/{job_id}/download"
    return job


@router.get("/scan/jobs/{job_id}/download")
def download_scan(job_id: str):
    """The finished scan. 409 while it isn't done — the phone should poll
    the status endpoint, whose done state carries this link."""
    job = _get_job_or_404(job_id)
    if job.status != ScanStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=f"Scan is '{job.status}' — there is nothing to download "
            "until it's done.",
        )
    path = downloads.result_path(job_id, SCAN_FILE_EXT[job.format])
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="The scanned file is gone — it may have been swept. Scan again.",
        )
    return FileResponse(path, filename=job.filename)


@router.delete("/scan/jobs/{job_id}", response_model=ScanJob)
def cancel_scan(job_id: str, _: None = Depends(require_pin)):
    """Cancel a queued/scanning scan and clean up whatever landed.

    A transfer already in flight cannot be interrupted mid-COM-call — the
    pipeline notices the cancellation after the transfer and discards the
    result (SCAN_PLAN §5). This endpoint removes whatever is already on
    disk; the pipeline does the same if it notices first.
    """
    _get_job_or_404(job_id)
    ok, message = scan_jobs.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    downloads.delete_job_files(job_id)
    logger.info("scan job %s cancelled", job_id)
    return scan_jobs.get_job(job_id)


def _get_job_or_404(job_id: str) -> ScanJob:
    job = scan_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"No scan job with id '{job_id}'."
        )
    return job
