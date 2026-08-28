"""Pydantic models: the shape of the API's requests/responses (SOURCE_OF_TRUTH Section 11)."""

from datetime import datetime

from pydantic import BaseModel


class PrintAccepted(BaseModel):
    """Response for POST /print.

    status is "received" until Phase 5 hands the file to the Windows print
    queue — then it becomes "queued", matching the API design in Section 11.
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


class JobStatus:
    """The lifecycle of a job. String constants keep the JSON simple.

    received → queued → printing → done
                     ↘ failed
    received (or queued, once P5 submits to Windows) → cancelled
    """

    RECEIVED = "received"
    QUEUED = "queued"
    PRINTING = "printing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

