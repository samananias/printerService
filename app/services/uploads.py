"""Upload handling (Phase 4; generalized for multi-format in p10).

Lifecycle of an uploaded file:
    phone → POST /print → validated here → uploads/<job_id><ext>
          → pipeline converts to uploads/<job_id>.pdf → printed → deleted

The PDF-only days enforced one rule ("is this a PDF?"); the multi-format
service enforces a policy instead (docs/MULTI_FORMAT_PLAN.md §6/§9):

    0. Macro-enabled Office formats are refused outright — policy, not
       technology (rejecting is cheaper than trusting a converter not to
       run their macros).
    1. The extension is a hint; app/detection.py decides what the file
       really is, using magic bytes.
    2. A binary format must actually show its signature — a renamed file
       fails here even though its extension looks right.
    3. A detected format is only accepted when a processor is registered
       for it (app/processors) — image/office/text stay refused until
       their phases land.
    4. The size limit still protects memory and disk from hostile uploads.

Anything still in uploads/ when the service starts is stale (the previous
run died before cleanup), so the app sweeps it on startup — the cheap
insurance SOURCE_OF_TRUTH Section 8 asks for. uploads/ is service-managed
(every name in it is server-generated), so the sweep now removes ANY file,
not just PDFs.
"""

import uuid
from pathlib import Path

from app.config import MAX_UPLOAD_MB, UPLOAD_DIR
from app.detection import (
    EXTENSION_CATEGORIES,
    MACRO_EXTENSIONS,
    category_for,
    magic_category,
)
from app.processors import for_category, supported_categories

# For a REGISTERED-but-unavailable processor: the message must tell the
# phone user what to do (office is the case today — LibreOffice missing or
# the ENABLE_OFFICE kill switch).
UNAVAILABLE_MESSAGES = {
    "office": (
        "Office printing is unavailable on this server — LibreOffice is not "
        "installed, or ENABLE_OFFICE=0 in .env. Convert the document to PDF "
        "first, or install LibreOffice to enable office formats."
    ),
}


class UploadError(Exception):
    """Raised with a human-readable reason; the API turns it into a 4xx error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def upload_path(job_id: str, ext: str = ".pdf") -> Path:
    """Where an upload with this job id lives on disk.

    Every module that needs to find a stored upload goes through here, so
    the location is defined once — and tests can redirect it in one place.
    """
    return UPLOAD_DIR / f"{job_id}{ext}"


def job_files(job_id: str) -> list[Path]:
    """Every file belonging to a job: the source upload and — once non-PDF
    formats exist — its converted PDF alongside it. Defined once so the
    pipeline's cleanup and the cancel endpoint agree on what a job leaves
    behind."""
    ensure_upload_dir()
    return sorted(path for path in UPLOAD_DIR.glob(f"{job_id}.*") if path.is_file())


def delete_job_files(job_id: str) -> int:
    """Delete every file of a job. Returns how many were removed."""
    removed = 0
    for path in job_files(job_id):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass  # never let cleanup crash the service
    return removed


def validate_upload(filename: str, data: bytes) -> str:
    """Security gate for every upload (SOURCE_OF_TRUTH Section 8).

    Checks run cheapest-first; returns the detected category ("pdf" in
    Phase 1) that the API records on the job and the pipeline dispatches
    on.
    """
    # 0. Macro policy — before any content parsing even looks at the file.
    ext = Path(filename).suffix.lower() if filename else ""
    if ext in MACRO_EXTENSIONS:
        raise UploadError(
            f"Macro-enabled Office files ({ext}) are not accepted for security "
            "reasons. Re-save the document without macros as a plain "
            ".docx/.xlsx/.pptx, or export a PDF.",
            status_code=415,
        )

    # 1+2. Extension hint vs magic evidence (app/detection.py): the allowlist
    #    stays explicit — an unknown extension is refused even when the
    #    content itself is recognizable (a lying "virus.exe" must not sneak
    #    in just because it happens to contain a PDF). When both sides are
    #    known they must agree; a binary format must show its signature.
    if ext and ext not in EXTENSION_CATEGORIES:
        raise UploadError(
            f"Unsupported file type '{ext}'. Currently supported: .pdf — "
            "more formats arrive in later phases.",
            status_code=415,
        )
    claimed = category_for(filename)
    content = magic_category(data)
    category = claimed or content
    if category is None:
        raise UploadError(
            "Unsupported file type '(no extension)'. Currently supported: "
            ".pdf — more formats arrive in later phases.",
            status_code=415,
        )
    if content is not None and content != category:
        raise UploadError(
            f"File content does not match the '{ext or '(none)'}' extension "
            f"(content looks like {content} data).",
            status_code=415,
        )
    if category in {"pdf", "image", "office"} and content is None:
        # Binary formats must show their signature; text is the only
        # extension-trusted category (see detection.py).
        reason = {
            "pdf": "File content is not a PDF (missing %PDF- header).",
            "image": "File content does not look like an image.",
            "office": "File content does not look like an Office document.",
        }[category]
        raise UploadError(reason, status_code=415)

    # 3. Availability — two distinct gates, two distinct messages:
    #    (a) no processor registered yet → "arrives in a later phase";
    #    (b) registered but not runnable on THIS machine (office kill
    #        switch / LibreOffice missing) → an actionable message.
    processor = for_category(category)
    if processor is None:
        printable = ", ".join(supported_categories())
        raise UploadError(
            f"'{ext or 'this format'}' files cannot be printed yet — support "
            f"arrives in a later phase. Currently printable: {printable}.",
            status_code=415,
        )
    if not processor.available():
        raise UploadError(
            UNAVAILABLE_MESSAGES.get(
                category,
                f"'{ext or category}' printing is unavailable on this server.",
            ),
            status_code=415,
        )

    # 4. Size limit — protects memory and disk from huge or hostile uploads.
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise UploadError(
            f"File is {len(data) / 1_000_000:.1f} MB; limit is {MAX_UPLOAD_MB} MB.",
            status_code=413,
        )
    return category


def save_upload(data: bytes, ext: str = ".pdf") -> tuple[str, Path]:
    """Store the bytes under a unique name. Returns (job_id, saved_path)."""
    ensure_upload_dir()
    job_id = uuid.uuid4().hex[:12]  # short, unique, no secrets in it
    path = upload_path(job_id, ext)
    path.write_bytes(data)
    return job_id, path


def sweep_stale_uploads() -> int:
    """Delete leftovers from a previous run. Returns how many were removed."""
    ensure_upload_dir()
    removed = 0
    for stale in UPLOAD_DIR.iterdir():
        if not stale.is_file():
            continue  # directories (or oddities) are skipped, not deleted
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass  # never let cleanup crash the service
    return removed
