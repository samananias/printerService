"""Job submission pipeline (Phase 5; multi-format in p10) — turns a stored
upload into paper.

Why a background thread: printing a PDF can take seconds. Doing it inside
the HTTP request would make the phone wait with no feedback; instead the
upload response returns immediately with status "queued" (matching the
Section 11 API design), and the job's status moves forward in the store.

The multi-format shape (docs/MULTI_FORMAT_PLAN.md §3/§8):

    detect (upload time) → processor → PDF → submit_pdf → Windows queue

PDF is the service's ONE internal print format: every category is turned
into a PDF before submit_pdf() ever sees it, so the print engine stays
byte-for-byte what Phase 5 proved with real paper (spike T4).

The job's states now move:

    received → queued → converting → printing → done
                                       ↘ failed

`printing` used to be defined but never set; it now wraps the actual
submission, and `converting` covers the (future) slow office conversions
so the phone can tell "working on your DOCX" from "talking to the printer".

The conversion lock: at most ONE conversion runs at a time. On the
print-server PC (≤4 GB RAM) that keeps future LibreOffice conversions from
stacking up; the PDF pass-through holds it for microseconds, and Windows'
own print queue keeps serializing actual printing between concurrent jobs
(SOURCE_OF_TRUTH Section 2).
"""

import logging
import threading
from pathlib import Path

from app.models.printing import JobStatus
from app.printer import windows
from app.processors import for_category
from app.services import jobs, uploads

logger = logging.getLogger(__name__)

# The old-PC guard: one conversion at a time, job or no job.
_conversion_lock = threading.Lock()


def start_job(job_id: str, src: Path, category: str = "pdf") -> None:
    """Hand a freshly uploaded job to a background submission thread."""
    jobs.update_status(job_id, JobStatus.QUEUED)
    threading.Thread(
        target=_process,
        args=(job_id, src, category),
        name=f"print-{job_id}",
        daemon=True,  # never block service shutdown on a stuck print job
    ).start()


def _process(job_id: str, src: Path, category: str) -> None:
    try:
        pdf_path = src
        processor = for_category(category)
        if processor is not None:
            jobs.update_status(job_id, JobStatus.CONVERTING)
            with _conversion_lock:
                pdf_path = processor.process(src, src.parent)

        jobs.update_status(job_id, JobStatus.PRINTING)
        method, printer = windows.submit_pdf(pdf_path)
        jobs.update_status(job_id, JobStatus.DONE, printer=printer)
        logger.info(
            "job %s (%s) submitted via %s to %r", job_id, category, method, printer
        )

        # Temp-file lifecycle (Section 8): printed → no longer needed.
        # Covers the source upload AND the converted PDF in one sweep.
        uploads.delete_job_files(job_id)

    except Exception as exc:
        logger.exception("job %s failed", job_id)
        # Keep the stored file(s) on failure — useful for diagnosing, and the
        # startup sweep (Phase 4) eventually clears them.
        jobs.update_status(job_id, JobStatus.FAILED, error=str(exc))
