"""Pydantic models for the scan feature (docs/SCAN_PLAN.md §4).

Scan keeps its own models, separate from printing's — the same reason it
gets its own job store later: "printing" language doesn't fit a scan, and
the scan feature must never reach into print code (SCAN_PLAN §4).
"""

from datetime import datetime

from pydantic import BaseModel


class ScanDevice(BaseModel):
    """One scanner Windows' WIA layer reports (a GET /scanners entry)."""

    name: str
    id: str


class ScannersInfo(BaseModel):
    """The GET /scanners response.

    available=false with an empty devices list is a NORMAL, healthy answer
    on a scanner-less setup (SCAN_PLAN §1 answer 5) — the web page uses it
    to decide whether to render the Scan section at all.
    """

    available: bool
    devices: list[ScanDevice]


class ScanStatus:
    """The scan lifecycle (SCAN_PLAN §5) — deliberately shorter than
    print's: no conversion step, WIA either hands back an image or not.

    queued → scanning → done
               ↘ failed
    queued or scanning → cancelled
    """

    QUEUED = "queued"
    SCANNING = "scanning"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanAccepted(BaseModel):
    """Response for POST /scan (SCAN_PLAN §4): accepted immediately — the
    transfer runs in a background thread. Poll GET /scan/jobs/{id}."""

    job_id: str
    status: str


class ScanJob(BaseModel):
    """One tracked scan job — the scan store's own shape. Deliberately no
    print columns (printer, options, category): a scan is not a print job
    in either direction (SCAN_PLAN §4)."""

    job_id: str
    filename: str  # the download name the phone sees (server-generated)
    size_bytes: int = 0
    status: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    format: str = "pdf"  # what the finished file is (pdf/png/jpeg)
    download_url: str | None = None  # set by the API once done


# ---------------------------------------------------------------------------
# Scan options (SCAN_PLAN §8 Phase 4) — strict allowlists, same spirit as
# the print side's Phase 7 options (MULTI_FORMAT_PLAN.md §10): validated
# BEFORE anything touches WIA, exactly like print options are validated
# before they touch a command line.
# ---------------------------------------------------------------------------

# DPI choices sized against the spike's real timings (S2: 200 dpi ≈ 41 s
# solo, 56 s with a concurrent print; 300 will be slower, 150 faster).
# 200 is the spike-verified default.
SCAN_DPI_CHOICES = (150, 200, 300)
SCAN_COLOR_MODES = ("color", "greyscale")
SCAN_FORMATS = ("pdf", "png", "jpeg")
DEFAULT_DPI = 200

# The on-disk extension a finished scan gets; the phone's download name
# follows it (scan-<id>.pdf/.png/.jpg).
SCAN_FILE_EXT = {"pdf": "pdf", "png": "png", "jpeg": "jpg"}


class ScanOptions(BaseModel):
    """Validated scan options attached to a scan job."""

    dpi: int = DEFAULT_DPI
    color_mode: str = "color"
    format: str = "pdf"


def validate_scan_options(dpi: int, color_mode: str, format: str) -> ScanOptions:
    """Validate raw form input and return normalized ScanOptions.

    Raises ValueError with a phone-user-readable message — the API layer
    maps that to HTTP 422, exactly like validate_print_options.
    """
    try:
        dpi = int(dpi)
    except (TypeError, ValueError):
        raise ValueError("DPI must be a number (150, 200 or 300).")
    if dpi not in SCAN_DPI_CHOICES:
        raise ValueError(
            f"DPI must be one of: {', '.join(map(str, SCAN_DPI_CHOICES))}."
        )

    color_mode = (color_mode or "color").strip().lower()
    if color_mode not in SCAN_COLOR_MODES:
        raise ValueError("Color mode must be 'color' or 'greyscale'.")

    format = (format or "pdf").strip().lower()
    if format not in SCAN_FORMATS:
        raise ValueError("Format must be 'pdf', 'png' or 'jpeg'.")

    return ScanOptions(dpi=dpi, color_mode=color_mode, format=format)
