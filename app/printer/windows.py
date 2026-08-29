"""
Windows printing code (Phase 5).

Importing win32print at module level would crash the whole service on any
machine without pywin32 (e.g. a non-Windows dev box), so the import happens
inside the functions. The service stays bootable everywhere; only printing
endpoints report a problem — exactly like SOURCE_OF_TRUTH Section 4 wants.

How a PDF gets printed (decision recorded in SOURCE_OF_TRUTH Section 5,
based on the spike run: the Windows "print" verb had no registered PDF
handler, WinError 1155):

  1. PRIMARY — SumatraPDF's command line:
       SumatraPDF.exe -print-to "<printer>" -silent <file.pdf>
     Silent, targets a named printer, no UI, we control the install.
  2. FALLBACK — Windows' "print" verb (os.startfile). Prints to the DEFAULT
     printer and depends on a registered PDF handler; kept only as a
     safety net.
  3. LAST RESORT (not implemented) — PDF→image conversion; build it only if
     SumatraPDF fails everywhere.

'DONE' job status means the spooler accepted the job and Sumatra returned
successfully — the physical printer may still be draining its queue.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.config import PAPER_SIZE, PRINTER_NAME, SUMATRA_PATH
from app.models.printing import PrinterInfo

logger = logging.getLogger(__name__)

SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
]


def get_default_printer() -> str:
    import win32print

    return win32print.GetDefaultPrinter()


def list_printers() -> list[PrinterInfo]:
    """Ask Windows which printers exist and which is the default (GET /printers)."""
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = sorted(p[2] for p in win32print.EnumPrinters(flags))
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = None
    return [PrinterInfo(name=name, is_default=(name == default)) for name in names]


def find_sumatra() -> str | None:
    """Locate SumatraPDF.exe. An explicitly configured path is authoritative:
    if it's set but missing, we report it missing rather than silently
    falling back (misconfigurations should be loud)."""
    if SUMATRA_PATH:
        return SUMATRA_PATH if os.path.isfile(SUMATRA_PATH) else None
    found = shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")
    if found:
        return found
    for candidate in SUMATRA_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_printer_name() -> str:
    """The printer jobs are submitted to: PRINTER_NAME config, else the
    Windows default. Used by submit_pdf and the cancel endpoint's spooler
    purge."""
    return PRINTER_NAME or get_default_printer()


def cancel_spooler_jobs(printer_name: str, job_id: str) -> int:
    """Best-effort removal of OUR queued jobs from the Windows spooler.

    SumatraPDF names the spooler document after the file it prints, and
    the service names that file <job_id>.pdf — so matching the document
    name against job_id finds our jobs without tracking Windows job ids.
    Best-effort per job: paper that already reached the printer cannot be
    recalled. Returns how many spooler jobs were removed.
    """
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        removed = 0
        for job in win32print.EnumJobs(handle, 0, -1, 1):
            document = job.get("pDocument") or ""
            if document.startswith(job_id):
                try:
                    win32print.SetJob(
                        handle,
                        job["JobId"],
                        0,
                        None,
                        win32print.JOB_CONTROL_DELETE,
                    )
                    removed += 1
                except Exception:
                    logger.warning(
                        "could not purge spooler job %s", job.get("JobId")
                    )
        return removed
    finally:
        win32print.ClosePrinter(handle)


def submit_pdf(pdf_path: Path, printer_name: str | None = None) -> tuple[str, str]:
    """Print a PDF file. Returns (method_used, printer_name).

    Raises RuntimeError with a human-readable reason on any failure — the
    caller (app/services/pipeline.py) records it as the job's error.
    """
    import win32print  # noqa: F401 — fail fast if pywin32 is missing

    if printer_name is None:
        printer_name = resolve_printer_name()

    sumatra = find_sumatra()
    if sumatra:
        logger.info("printing %s via SumatraPDF to %r", pdf_path.name, printer_name)
        cmd = [sumatra, "-print-to", printer_name]
        if PAPER_SIZE:
            # Opt-in paper pinning (PAPER_SIZE in .env). Empty = no print
            # settings at all — the driver chooses, which is the exact
            # behavior spike T4 proved on real paper. "fit" scales content
            # instead of clipping it when page and paper disagree.
            cmd += ["-print-settings", f"paper={PAPER_SIZE},fit"]
        cmd += ["-silent", str(pdf_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SumatraPDF failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
        return "sumatrapdf", printer_name

    # Fallback: Windows' "print" verb. Limitations (Section 5): prints to the
    # DEFAULT printer only, and needs a PDF app that registered the verb —
    # the spike showed this machine has none (WinError 1155).
    if printer_name != get_default_printer():
        raise RuntimeError(
            "No PDF printing method available: SumatraPDF was not found, and "
            f"the requested printer {printer_name!r} is not the Windows "
            "default (the print-verb fallback can only use the default). "
            "Install SumatraPDF and set SUMATRA_PATH if needed."
        )

    logger.info("printing %s via print verb to default printer", pdf_path.name)
    os.startfile(str(pdf_path), "print")  # == ShellExecute(verb="print")
    return "shell-print-verb", printer_name

