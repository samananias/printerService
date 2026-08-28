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

    def process(self, src: Path, out_dir: Path) -> Path:
        """Convert `src` into a print-ready PDF and return that PDF's path.

        `out_dir` is the directory to write the converted file into
        (uploads/, next to the original) so cleanup stays one glob away.
        """
        ...
