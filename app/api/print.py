"""
POST /print — accept a PDF upload (Phase 4).

Printing itself arrives in Phase 5; this endpoint proves the *transfer* half
of the pipeline: phone → HTTP → validated bytes on disk, intact.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.printing import PrintAccepted
from app.services import jobs
from app.services.uploads import UploadError, save_upload, validate_pdf

router = APIRouter()


@router.post("/print", response_model=PrintAccepted, status_code=201)
async def print_pdf(file: UploadFile = File(...)):
    """Accept a PDF exactly like a web form uploads a photo: a
    multipart/form-data POST whose file field is named "file".

    Flow (SOURCE_OF_TRUTH Section 5, stages 2-4):
      1. FastAPI/python-multipart parse the request and hand us the bytes.
      2. validate_pdf() applies the Section 8 checks (type, size).
      3. save_upload() stores them under a unique job_id in uploads/.
      4. The job is registered in the in-memory tracker (Phase 7).

    Returns 201 with the job id. Errors: 415 (not a PDF), 413 (too large).
    """
    data = await file.read()

    try:
        validate_pdf(file.filename or "", data)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    job_id, _path = save_upload(data)
    jobs.create_job(job_id, file.filename or "unknown.pdf", len(data), _path)

    return PrintAccepted(
        job_id=job_id,
        status="received",
        filename=file.filename or "unknown.pdf",
        size_bytes=len(data),
    )
