"""
Upload handling (Phase 4): validation + temporary storage.

Lifecycle of an uploaded file:
    phone → POST /print → validated here → uploads/<job_id>.pdf
          → (Phase 5) handed to the Windows print queue → deleted

Anything still in uploads/ when the service starts is stale (the previous
run died before cleanup), so the app sweeps it on startup — the cheap
insurance SOURCE_OF_TRUTH Section 8 asks for.
"""

import uuid
from pathlib import Path

from app.config import MAX_UPLOAD_MB, PDF_MAGIC, UPLOAD_DIR


class UploadError(Exception):
    """Raised with a human-readable reason; the API turns it into a 4xx error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def validate_pdf(filename: str, data: bytes) -> None:
    """Three checks, cheapest first (SOURCE_OF_TRUTH Section 8)."""

    # 1. Extension hint — a cheap first look, but extensions can lie.
    if filename and not filename.lower().endswith(".pdf"):
        raise UploadError("Only .pdf files are accepted.", status_code=415)

    # 2. Magic bytes — what a file CLAIMS to be matters less than what it IS.
    #    A real PDF always begins with the bytes b"%PDF-"; a renamed .txt
    #    fails here even though it ends in ".pdf".
    if not data.startswith(PDF_MAGIC):
        raise UploadError(
            "File content is not a PDF (missing %PDF- header).",
            status_code=415,
        )

    # 3. Size limit — protects memory and disk from huge or hostile uploads.
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise UploadError(
            f"File is {len(data) / 1_000_000:.1f} MB; limit is {MAX_UPLOAD_MB} MB.",
            status_code=413,
        )


def save_upload(data: bytes) -> tuple[str, Path]:
    """Store the bytes under a unique name. Returns (job_id, saved_path)."""
    ensure_upload_dir()
    job_id = uuid.uuid4().hex[:12]  # short, unique, no secrets in it
    path = UPLOAD_DIR / f"{job_id}.pdf"
    path.write_bytes(data)
    return job_id, path


def sweep_stale_uploads() -> int:
    """Delete leftovers from a previous run. Returns how many were removed."""
    ensure_upload_dir()
    removed = 0
    for stale in UPLOAD_DIR.glob("*.pdf"):
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass  # never let cleanup crash the service
    return removed
