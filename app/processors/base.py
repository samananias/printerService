"""The Processor contract (multi-format plan, docs/MULTI_FORMAT_PLAN.md §3).

A processor turns ONE category of uploaded file into the service's single
internal print format: a PDF. Everything downstream of the processors —
the pipeline, `submit_pdf()`, SumatraPDF, the Windows queue — only ever
sees a PDF, which is exactly what spike T4 proved prints reliably on the
L3210.

This is the seam that keeps the print engine format-agnostic forever:
adding a format means writing one processor and registering it in
app/processors/__init__.py — the pipeline never changes.
"""

from pathlib import Path
from typing import Protocol

from app.config import PAPER_SIZE

# Shared page geometry (points; 1 pt = 1/72"). Processors that AUTHOR pages
# (images, text) lay their content out on this size; unknown/empty
# PAPER_SIZE falls back to A4. Add entries (e.g. long bond 8.5x13) as later
# phases need them.
PAGE_SIZES_PT = {
    "a3": (842, 1191),
    "a4": (595, 842),
    "a5": (420, 595),
    "letter": (612, 792),
    "legal": (612, 1008),
}
DEFAULT_PAGE = "a4"


def page_size_pt() -> tuple[int, int]:
    """The page authored content sits on: PAPER_SIZE when it names a known
    size, A4 otherwise (a page must be concrete before anything fits on it)."""
    return PAGE_SIZES_PT.get(PAPER_SIZE.strip().lower(), PAGE_SIZES_PT[DEFAULT_PAGE])


class ConversionError(Exception):
    """Raised with a human-readable reason when a file cannot be converted.

    The pipeline records the message as the job's error — write for the
    person holding the phone ("LibreOffice could not open the file: ..."),
    not for a log analyst.
    """


class Processor(Protocol):
    """One format category's conversion step.

    Implementations must be safe to run on the pipeline's background
    thread, must not modify `src`, and must return a path to a valid PDF.
    Long-running converters (LibreOffice, Phase 3) are subprocess calls
    with their own timeout + process-tree kill.
    """

    def available(self) -> bool:
        """Whether this processor can run on THIS machine right now.

        A processor can be registered but still disabled (the office kill
        switch) or missing its external tool (LibreOffice not installed).
        The upload gate checks this so users get an actionable message —
        "install LibreOffice / flip ENABLE_OFFICE" — instead of a job that
        dies later with a subprocess error.
        """
        ...

    def process(self, src: Path, out_dir: Path) -> Path:
        """Convert `src` into a print-ready PDF and return that PDF's path.

        `out_dir` is the directory to write the converted file into
        (uploads/, next to the original) so cleanup stays one glob away.
        """
        ...
