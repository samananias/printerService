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
    download_url: str | None = None  # set by the API once done
