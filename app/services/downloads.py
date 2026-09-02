"""downloads/ — where finished scans wait for the phone (SCAN_PLAN §5/§7).

Mirror of uploads.py's hygiene rules, scan side:

  - every filename in here is SERVER-generated (the job id) — the client
    never names scan files, which kills path traversal by construction;
  - a finished scan is kept until the phone grabs it (unlike a print, the
    file IS the deliverable — nothing "prints" it away), so the startup
    sweep is the cleanup safety net for crashed runs;
  - dotfiles (e.g. .gitkeep) survive the sweep, exactly like uploads/.
"""

import logging
from pathlib import Path

from app.config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)


def ensure_downloads_dir() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def result_path(job_id: str, ext: str = "pdf") -> Path:
    """The finished scan's location: downloads/<job_id>.<ext>.

    `ext` is the on-disk extension of the chosen format (pdf/png/jpg).
    Phase 2 shipped the one PDF format; Phase 4's format=png|jpeg escape
    hatch uses this to name the deliverable.
    """
    return DOWNLOAD_DIR / f"{job_id}.{ext}"


def working_path(job_id: str) -> Path:
    """The WIA transfer's raw PNG — wrapped into the PDF by the pipeline
    and deleted on success, kept on failure for diagnosing."""
    return DOWNLOAD_DIR / f"{job_id}.png"


def job_files(job_id: str) -> list[Path]:
    """Every file belonging to a scan job (raw PNG + finished PDF).
    Defined once so the pipeline's cleanup and the cancel endpoint agree
    on what a scan leaves behind."""
    ensure_downloads_dir()
    return sorted(p for p in DOWNLOAD_DIR.glob(f"{job_id}.*") if p.is_file())


def delete_job_files(job_id: str) -> int:
    """Delete every file of a scan job. Returns how many were removed."""
    removed = 0
    for path in job_files(job_id):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass  # never let cleanup crash the service
    return removed


def sweep_stale_downloads() -> int:
    """Startup safety net: a previous run that died left scan files with
    nobody to download them. Same rule as the uploads sweep — dotfiles
    are kept, everything else goes."""
    ensure_downloads_dir()
    removed = 0
    for stale in DOWNLOAD_DIR.iterdir():
        if not stale.is_file() or stale.name.startswith("."):
            continue  # directories (or oddities) and dotfiles are skipped
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass  # never let cleanup crash the service
    if removed:
        logger.info("swept %d stale download(s) from a previous run", removed)
    return removed
