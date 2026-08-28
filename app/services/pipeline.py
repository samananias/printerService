"""
Job submission pipeline (Phase 5) — turns a stored upload into paper.

Why a background thread: printing a PDF can take seconds. Doing it inside
the HTTP request would make the phone wait with no feedback; instead the
upload response returns immediately with status "queued" (matching the
Section 11 API design), and the job's status moves forward in the store:

    received → queued → done     (or failed, with a human-readable error)

Windows' own print queue serializes actual printing between concurrent
jobs (SOURCE_OF_TRUTH Section 2), so we don't need our own queue for v1.
"""

import logging
import threading
from pathlib import Path

from app.models.printing import JobStatus
from app.printer import windows
from app.services import jobs

logger = logging.getLogger(__name__)


def start_job(job_id: str, pdf_path: Path) -> None:
    """Hand a freshly uploaded job to a background submission thread."""
    jobs.update_status(job_id, JobStatus.QUEUED)
    threading.Thread(
        target=_process,
        args=(job_id, pdf_path),
        name=f"print-{job_id}",
        daemon=True,  # never block service shutdown on a stuck print job
    ).start()


def _process(job_id: str, pdf_path: Path) -> None:
    try:
        method, printer = windows.submit_pdf(pdf_path)
        jobs.update_status(job_id, JobStatus.DONE, printer=printer)
        logger.info("job %s submitted via %s to %r", job_id, method, printer)

        # Temp-file lifecycle (Section 8): printed → no longer needed.
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("could not delete %s after printing", pdf_path)

    except Exception as exc:
        logger.exception("job %s failed to print", job_id)
        # Keep the stored file on failure — useful for diagnosing, and the
        # startup sweep (Phase 4) eventually clears it.
        jobs.update_status(job_id, JobStatus.FAILED, error=str(exc))
