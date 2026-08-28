"""Office processor (Phase 3) — DOCX/XLSX/PPTX (and legacy/ODF) via
LibreOffice Headless.

LibreOffice converts each document to the service's one print format (a
PDF) in a subprocess; the conversion runs inside the pipeline's conversion
lock, so at most ONE LibreOffice instance exists at a time — the old-PC
guard (≤4 GB RAM, MULTI_FORMAT_PLAN.md §6 load profile).

Invocation (security notes in MULTI_FORMAT_PLAN.md §9):

    soffice --headless --norestore --nolockcheck
            -env:UserInstallation=<fresh throwaway profile>
            --convert-to pdf --outdir <out_dir> <src>

- headless: no GUI, no desktop needed; it does not execute document macros.
- a FRESH throwaway user profile per conversion: a crashed earlier run can
  never poison the next one (stale locks), and someone running LibreOffice's
  GUI on the default profile can never clash with us. Costs ~1s of profile
  warmup per document — worth the robustness on a home server.
- CONVERT_TIMEOUT_S bounds the whole conversion; on timeout the whole
  process TREE is killed (soffice spawns soffice.bin children).

Quality expectations (MULTI_FORMAT_PLAN.md §7): layout fidelity is
LibreOffice's, so fonts installed on THIS server matter (missing fonts get
substituted and line breaks shift); an XLSX saved without a print area
paginates all columns. spike_t6_office.py verifies on real paper — it is
this phase's acceptance gate.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.config import CONVERT_TIMEOUT_S, ENABLE_OFFICE, LO_PATH
from app.processors.base import ConversionError

logger = logging.getLogger(__name__)

SOFFICE_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def find_soffice() -> str | None:
    """Locate soffice.exe. An explicitly configured LO_PATH is authoritative:
    if it's set but missing, we report it missing rather than silently
    falling back (misconfigurations should be loud) — the same rule as
    SUMATRA_PATH."""
    if LO_PATH:
        return LO_PATH if Path(LO_PATH).is_file() else None
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for candidate in SOFFICE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


class OfficeProcessor:
    """Converts office documents to PDF. Depends on an external LibreOffice
    install — the service's only heavyweight dependency, gated behind
    ENABLE_OFFICE so it can be switched off without uninstalling."""

    def available(self) -> bool:
        return ENABLE_OFFICE and find_soffice() is not None

    def process(self, src: Path, out_dir: Path) -> Path:
        soffice = find_soffice()
        if soffice is None:
            # Only reachable if the machine changed between upload and
            # conversion (e.g. ENABLE_OFFICE flipped mid-queue) — fail with
            # the message the user needs, not a subprocess traceback.
            raise ConversionError(
                "LibreOffice is not available on this server, so this "
                "document cannot be converted. Convert it to PDF first."
            )

        pdf_path = out_dir / f"{src.stem}.pdf"
        try:
            profile = tempfile.TemporaryDirectory(
                prefix="lo-profile-", ignore_cleanup_errors=True
            )
        except OSError as exc:
            raise ConversionError(f"Could not create a temp profile dir: {exc}") from exc

        with profile:
            cmd = [
                soffice,
                "--headless",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation={Path(profile.name).as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(src),
            ]
            started = time.perf_counter()
            try:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            except OSError as exc:
                raise ConversionError(f"Could not start LibreOffice: {exc}") from exc

            try:
                _stdout, stderr = process.communicate(timeout=CONVERT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                self._kill_tree(process)
                raise ConversionError(
                    f"LibreOffice did not finish within {CONVERT_TIMEOUT_S}s — "
                    "the document may be too complex. Try exporting a PDF "
                    "from the app it was made in."
                ) from None

            if process.returncode != 0:
                raise ConversionError(
                    f"LibreOffice failed (exit {process.returncode}): "
                    f"{stderr.decode(errors='replace').strip()[:500]}"
                )
            if not pdf_path.is_file():
                # soffice can exit 0 without producing output (e.g. an
                # unreadable file it chose not to complain about).
                raise ConversionError(
                    "LibreOffice reported success but produced no PDF — the "
                    "document may be corrupt or use an unsupported feature."
                )

            logger.info(
                "converted %s -> %s in %.1fs (LibreOffice)",
                src.name,
                pdf_path.name,
                time.perf_counter() - started,
            )
            return pdf_path

    @staticmethod
    def _kill_tree(process: subprocess.Popen) -> None:
        """Kill soffice AND its children — it runs the real work in a
        soffice.bin child, so killing the direct process is not enough."""
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
            )
        else:
            process.kill()
        process.communicate()  # reap so nothing is left hanging


# Stateless → one shared instance for every job (conversions are serialized
# by the pipeline's conversion lock).
OFFICE_PROCESSOR = OfficeProcessor()
