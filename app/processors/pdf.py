"""PDF pass-through processor (Phase 1).

PDF already IS the service's internal print format, so "conversion" is a
no-op that returns the source unchanged. It exists so every category flows
through the same pipeline code path — detect → processor → print engine —
with no PDF special case anywhere.
"""

from pathlib import Path


class PdfProcessor:
    def process(self, src: Path, out_dir: Path) -> Path:
        # Source bytes were validated at upload time (magic + size); the
        # real "can Sumatra open it" check happens when Sumatra runs, and
        # its exit code 2 becomes a job error with a human message.
        return src


# Stateless → one shared instance for every job.
PDF_PROCESSOR = PdfProcessor()
