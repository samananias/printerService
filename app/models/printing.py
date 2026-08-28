"""Pydantic models: the shape of the API's requests/responses (SOURCE_OF_TRUTH Section 11)."""

from pydantic import BaseModel


class PrintAccepted(BaseModel):
    """Response for POST /print.

    status is "received" while the upload is validated+stored only (Phase 4).
    In Phase 5, when the file is handed to the Windows print queue, the
    status becomes "queued" — matching the API design in Section 11.
    """

    job_id: str
    status: str
    filename: str
    size_bytes: int
