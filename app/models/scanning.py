"""Pydantic models for the scan feature (docs/SCAN_PLAN.md §4).

Scan keeps its own models, separate from printing's — the same reason it
gets its own job store later: "printing" language doesn't fit a scan, and
the scan feature must never reach into print code (SCAN_PLAN §4).
"""

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
