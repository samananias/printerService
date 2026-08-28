"""
POST /print — accept a printable file (Phase 4; multi-format in p10).

Printing itself arrives in Phase 5's background thread; this endpoint
proves the *transfer* half of the pipeline: phone → HTTP → validated bytes
on disk, intact.

Phase 1 (multi-format refactor) keeps the behavior PDF-only, but the flow
is now format-agnostic (docs/MULTI_FORMAT_PLAN.md §8):

  1. FastAPI/python-multipart parse the request and hand us the bytes.
  2. validate_upload() applies the Section 8 checks (type, content,
     availability, size) and returns the detected category. A category
     prints once its processor is registered (app/processors) — PDF and
     images today; office/text arrive in later phases and are refused
     with a "support arrives in a later phase" message until then.
  3. save_upload() stores the bytes under a unique job id, keeping the
     real extension.
  4. The job is registered (category recorded) and handed to the
     background pipeline: convert → print → cleanup.

Returns 201 with the job id. Errors: 401 (bad PIN), 415 (unsupported file
or lying extension), 413 (too large), 500 (disk trouble).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.detection import DEFAULT_EXTENSIONS
from app.models.printing import PrintAccepted
from app.services import jobs, pipeline
from app.services.auth import require_pin
from app.services.uploads import UploadError, save_upload, validate_upload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/print", response_model=PrintAccepted, status_code=201)
async def print_file(
    file: UploadFile = File(...),
    _: None = Depends(require_pin),  # PIN required only when API_PIN is set
):
    """Accept a file exactly like a web form uploads a photo: a
    multipart/form-data POST whose file field is named "file"."""
    data = await file.read()
    filename = file.filename or ""

    try:
        category = validate_upload(filename, data)
    except UploadError as exc:
        logger.warning("rejected upload %r: %s", filename, exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    # Store under the real extension; a client that sent no usable filename
    # gets the canonical one for its (magic-proven) category.
    ext = Path(filename).suffix.lower() or DEFAULT_EXTENSIONS[category]

    try:
        job_id, path = save_upload(data, ext=ext)
    except OSError as exc:
        # Disk full, permissions, antivirus blocking writes... a clean 500
        # beats an unhandled exception crashing the request (Section 14).
        logger.exception("could not store upload %r", filename)
        raise HTTPException(status_code=500, detail=f"Could not store upload: {exc}")

    jobs.create_job(job_id, filename or f"unknown{ext}", len(data), path, format=category)
    pipeline.start_job(job_id, path, category)
    logger.info(
        "job %s received: %s (%d bytes, %s)", job_id, filename, len(data), category
    )

    return PrintAccepted(
        job_id=job_id,
        status="queued",
        filename=filename or f"unknown{ext}",
        size_bytes=len(data),
    )
