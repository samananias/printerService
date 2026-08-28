"""Format detection — "what kind of file is this, really?" (multi-format
plan, docs/MULTI_FORMAT_PLAN.md Section 3).

Detection is deliberately separate from "what can we print": the printable
gate lives in app/processors (a category becomes printable only once a
processor is registered for it). Phase 1 registers only "pdf"; image,
office and text arrive in Phases 2–4 without touching this module again.

Rules, cheapest first (SOURCE_OF_TRUTH Section 8):

1. The extension is only a HINT — extensions lie, so nothing is accepted
   on the extension alone.
2. Every supported binary format has a fixed magic signature; the
   signature wins whenever it disagrees with the extension.
3. ZIP and OLE containers hold several formats (DOCX/XLSX/PPTX/ODF all
   start with PK), so the container is opened and its entry names are
   sniffed to confirm it really is an office document.
4. Plain text (.txt/.csv) has no magic bytes: it is classified by
   extension, and its decodability is verified later by its processor
   (Phase 4).

This module knows nothing about HTTP — uploads.py maps classification
failures to 415 responses.
"""

import zipfile
from io import BytesIO
from pathlib import Path

from app.config import PDF_MAGIC

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_MAGIC = b"RIFF"  # a RIFF container; b"WEBP" must follow at offset 8
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy DOC/XLS/PPT
ZIP_MAGIC = b"PK\x03\x04"  # OOXML (DOCX/XLSX/PPTX) and ODF containers

# Categories whose files MUST carry their magic signature. Text is the
# exception: bytes that are "just text" are indistinguishable from any
# other content, so .txt/.csv are trusted at upload time and verified
# (decodable, sane) by their processor.
MAGIC_REQUIRED = frozenset({"pdf", "image", "office"})

# Macro-enabled Office formats are rejected outright, before any other
# check runs (plan Section 9). LibreOffice headless would not execute
# their macros, but rejecting is cheaper and safer than relying on that.
MACRO_EXTENSIONS = frozenset(
    {".docm", ".dotm", ".xlsm", ".xltm", ".pptm", ".potm"}
)

EXTENSION_CATEGORIES: dict[str, str] = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".bmp": "image",
    ".gif": "image",
    ".tif": "image",
    ".tiff": "image",
    ".doc": "office",
    ".docx": "office",
    ".xls": "office",
    ".xlsx": "office",
    ".ppt": "office",
    ".pptx": "office",
    ".odt": "office",
    ".ods": "office",
    ".odp": "office",
    ".txt": "text",
    ".csv": "text",
}

# Extension to store a file under when the client sent no usable filename
# (its category was proven by magic bytes instead).
DEFAULT_EXTENSIONS = {
    "pdf": ".pdf",
    "image": ".jpg",
    "office": ".docx",
    "text": ".txt",
}


def category_for(filename: str) -> str | None:
    """The category an extension claims, or None for unknown/absent names."""
    ext = Path(filename).suffix.lower() if filename else ""
    return EXTENSION_CATEGORIES.get(ext)


def magic_category(data: bytes) -> str | None:
    """The category the CONTENT claims, or None if no signature matches."""
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
        return "image"
    if data.startswith(WEBP_MAGIC) and data[8:12] == b"WEBP":
        return "image"
    if data.startswith(OLE_MAGIC):
        return "office"
    if data.startswith(ZIP_MAGIC) and _is_office_zip(data):
        return "office"
    return None


def _is_office_zip(data: bytes) -> bool:
    """Tell printable office containers from ordinary zip files.

    OOXML parts live under word/ (DOCX), xl/ (XLSX) or ppt/ (PPTX); ODF
    files carry a "mimetype" entry. Anything else is a zip we don't print.
    """
    try:
        names = zipfile.ZipFile(BytesIO(data)).namelist()
    except (zipfile.BadZipFile, OSError):
        return False
    return any(name.startswith(("word/", "xl/", "ppt/")) for name in names) or (
        "mimetype" in names
    )
