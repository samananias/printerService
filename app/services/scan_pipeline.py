"""Scan pipeline (docs/SCAN_PLAN.md §5, Phase 2) — turns an accepted scan
job into a PDF in downloads/.

Why a background thread: a flatbed transfer takes tens of seconds (spike
S2 measured 41.4 s at 200 dpi — 56.1 s while a print ran). Doing it inside
the HTTP request would make the phone wait with no feedback; the response
returns immediately with status "queued", and the job's status moves
forward in the store:

    queued → scanning → done
               ↘ failed

The pipeline's shape (SCAN_PLAN §5 step 3 — reused, not reinvented):

    WIA transfer (raw PNG, driver defaults) →
    REAL ImageProcessor — the print side's fit-to-page code, the exact
    reuse spike S3 proved on hardware →
    downloads/<job_id>.pdf → raw PNG deleted

Between every stage the job's status is re-checked: a cancel always wins
over the next step, and a cancelled scan is never marked done (the same
rule the print pipeline has followed since p14).
"""

import logging
import threading

from app.models.scanning import ScanStatus
from app.processors.images import IMAGE_PROCESSOR
from app.scanner.windows import scan_flatbed
from app.services import downloads, scan_jobs

logger = logging.getLogger(__name__)


def start_scan(job_id: str) -> None:
    """Hand a freshly accepted scan job to a background scan thread."""
    current = scan_jobs.get_job(job_id)
    if current is not None and current.status == ScanStatus.CANCELLED:
        # The cancel raced in between accept and this call — scanning
        # would resurrect it (update_status doesn't know better).
        logger.info("scan %s cancelled before it started — not scanning", job_id)
        downloads.delete_job_files(job_id)
        return
    scan_jobs.update_status(job_id, ScanStatus.QUEUED)
    threading.Thread(
        target=_process,
        args=(job_id,),
        name=f"scan-{job_id[:8]}",
        daemon=True,  # never block service shutdown on a stuck scan
    ).start()


def _cancelled(job_id: str) -> bool:
    """Whether the user cancelled — checked between stages so a cancel
    always wins over the next step."""
    job = scan_jobs.get_job(job_id)
    return job is not None and job.status == ScanStatus.CANCELLED


def _process(job_id: str) -> None:
    png_path = downloads.working_path(job_id)
    pdf_path = downloads.result_path(job_id)
    try:
        downloads.ensure_downloads_dir()  # fresh installs have no downloads/
        scan_jobs.update_status(job_id, ScanStatus.SCANNING)
        if _cancelled(job_id):
            _abandon(job_id, "before the transfer")
            return

        scan_flatbed(png_path)
        if _cancelled(job_id):
            _abandon(job_id, "after the transfer")
            return

        # The REAL production path for image → print-ready PDF: the same
        # fit/center/white-flatten code the print side uses for photo
        # uploads. process() names its output <stem>.pdf — exactly
        # result_path(job_id).
        pdf_path = IMAGE_PROCESSOR.process(png_path, downloads.DOWNLOAD_DIR)
        if _cancelled(job_id):
            _abandon(job_id, "after the wrap")
            return

        size = pdf_path.stat().st_size
        try:
            png_path.unlink()  # the deliverable is the PDF; drop the raw PNG
        except OSError:
            pass  # never let cleanup fail the job

        scan_jobs.update_status(job_id, ScanStatus.DONE, size_bytes=size)
        logger.info("scan %s done (%d bytes)", job_id, size)

    except Exception as exc:
        logger.exception("scan %s failed", job_id)
        # Keep whatever landed on disk — a raw PNG diagnoses WIA trouble.
        # The startup sweep is the eventual cleanup; there is no retry in
        # Phase 2 (the phone just scans again).
        scan_jobs.update_status(job_id, ScanStatus.FAILED, error=str(exc))


def _abandon(job_id: str, where: str) -> None:
    """Clean up after a cancellation noticed at a stage boundary — a
    cancelled scan's files are nobody's deliverable."""
    downloads.delete_job_files(job_id)
    logger.info("scan %s cancelled %s — nothing delivered", job_id, where)
