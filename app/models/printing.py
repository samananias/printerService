"""Pydantic models: the shape of the API's requests/responses (SOURCE_OF_TRUTH Section 11)."""

import re
from datetime import datetime

from pydantic import BaseModel


class PrintAccepted(BaseModel):
    """Response for POST /print.

    status is "queued": submission to the Windows print queue happens in a
    background thread (app/services/pipeline.py), so the response returns
    immediately. Poll GET /jobs/{id} to watch it move to done/failed.
    """

    job_id: str
    status: str
    filename: str
    size_bytes: int


class PrinterInfo(BaseModel):
    """One entry of GET /printers."""

    name: str
    is_default: bool


class PrintJob(BaseModel):
    """One tracked print job (in-memory store, Section 12 — no database yet)."""

    job_id: str
    filename: str
    size_bytes: int
    status: str
    created_at: datetime
    updated_at: datetime
    printer: str | None = None  # set in Phase 5 when actually submitted
    error: str | None = None
    format: str | None = None  # detected category ("pdf" today; image/office/text as phases land)
    options: dict | None = None  # Phase 7 print options (copies/pages/paper/color_mode)


class JobStatus:
    """The lifecycle of a job. String constants keep the JSON simple.

    received → queued → converting → printing → done
                     ↘ failed
    received (or queued, once P5 submits to Windows) → cancelled

    `converting` (p10) covers format conversion — a no-op for PDFs, but the
    visible step that explains why an office document takes tens of seconds.
    """

    RECEIVED = "received"
    QUEUED = "queued"
    CONVERTING = "converting"
    PRINTING = "printing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Print options (Phase 7 / v2) — per-request copies, page range, paper and
# color mode. One set of options works for EVERY format because processors
# normalize everything to PDF before the engine sees it.
# ---------------------------------------------------------------------------

# Paper keys shared by validation (here), page layout (processors/base
# PAGE_SIZES_PT) and the Sumatra tokens (printer/windows PAPER_TOKENS).
# "" = printer default. "long-bond" is 8.5×13" — bond-paper sizing.
PAPER_CHOICES = ("", "a4", "letter", "legal", "a3", "a5", "long-bond")
COLOR_MODES = ("color", "monochrome")

# Page selection allowlist: "odd"/"even", or a comma list of single pages
# and ranges ("5", "2-6", "1-3,5,8-10"). This is a STRICT allowlist — the
# string goes into a command line, so anything not matching is refused
# before it gets there. SumatraPDF understands reversed ranges (10-8), so
# start>end is allowed on purpose.
PAGES_PATTERN = re.compile(r"^(odd|even)$|^\d{1,3}(-\d{1,3})?(,\d{1,3}(-\d{1,3})?)*$")


class PrintOptions(BaseModel):
    """Validated print options attached to a job (stored with it, reused
    by retry)."""

    copies: int = 1
    pages: str = ""  # "" = the whole document
    paper: str = ""  # "" = config PAPER_SIZE, else the printer's default
    color_mode: str = "color"


def validate_print_options(
    copies: int, pages: str, paper: str, color_mode: str
) -> PrintOptions:
    """Validate raw form input and return normalized PrintOptions.

    Raises ValueError with a phone-user-readable message — the API layer
    maps that to HTTP 422.
    """
    if not 1 <= copies <= 99:
        raise ValueError("Copies must be between 1 and 99.")

    pages = (pages or "").strip()
    if len(pages) > 100:
        raise ValueError("The page selection is too long.")
    if pages and not PAGES_PATTERN.match(pages):
        raise ValueError(
            "Pages must look like '2-6', '1,3,5', '1-3,5' — or 'odd'/'even'."
        )

    paper = (paper or "").strip().lower()
    if paper not in PAPER_CHOICES:
        raise ValueError(
            f"Paper must be one of: {', '.join(c or 'printer default' for c in PAPER_CHOICES)}."
        )

    color_mode = (color_mode or "color").strip().lower()
    if color_mode not in COLOR_MODES:
        raise ValueError("Color mode must be 'color' or 'monochrome'.")

    return PrintOptions(
        copies=copies, pages=pages, paper=paper, color_mode=color_mode
    )

