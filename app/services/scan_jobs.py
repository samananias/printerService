"""Scan job store (docs/SCAN_PLAN.md §4/§5).

Deliberately NOT the print store (SCAN_PLAN §4): print's states and
columns ("printing", printer, options, category) don't fit a scan, and
the scan feature must never reach into print code. So: a separate
`scan_jobs` table in the SAME SQLite file (config: JOB_DB_PATH), owned by
this module with ITS OWN connection and ITS OWN RLock — app/services/
jobs.py's shared connection is never touched, which keeps the "scan never
modifies print code" guarantee literal.

Lifecycle (SCAN_PLAN §5, deliberately shorter than print's — there is no
conversion step; WIA either hands back an image or it doesn't):

    queued → scanning → done
               ↘ failed
    queued or scanning → cancelled

Startup recovery (recover_interrupted, called from main's lifespan, after
the downloads sweep) flips scans left queued/scanning by a crashed run to
failed — their files are gone either way, so there is nothing to deliver.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import JOB_DB_PATH
from app.models.scanning import SCAN_FILE_EXT, ScanJob, ScanStatus

# States a cancel may interrupt; done/failed/cancelled are terminal.
CANCELLABLE = frozenset({ScanStatus.QUEUED, ScanStatus.SCANNING})

_lock = threading.RLock()
_db_path = Path(JOB_DB_PATH)
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_jobs (
    job_id     TEXT PRIMARY KEY,
    filename   TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error      TEXT,
    format     TEXT NOT NULL DEFAULT 'pdf'
)
"""


def _get_conn() -> sqlite3.Connection:
    """The shared connection, created (with schema) on first use.

    Own connection, own lock (SCAN_PLAN §0 adjustment 4): a sqlite3
    connection must not be used from two threads at once, and each
    store's lock protects only its own — sharing jobs.py's would couple
    the two subsystems this feature is built to keep apart.
    """
    global _conn
    if _conn is None:
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(_db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(_SCHEMA)
        try:
            # Migrates databases created before Phase 4 (no format column).
            # "duplicate column" means the migration already ran.
            _conn.execute(
                "ALTER TABLE scan_jobs ADD COLUMN format TEXT NOT NULL DEFAULT 'pdf'"
            )
        except sqlite3.OperationalError:
            pass
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_job(row: sqlite3.Row) -> ScanJob:
    return ScanJob(
        job_id=row["job_id"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        error=row["error"],
        format=row["format"],
    )


def create_job(job_id: str, options: dict | None = None) -> ScanJob:
    """Register a freshly accepted scan: queued, file not yet on disk.

    The filename is the download name the phone will see — server
    generated like everything else in downloads/ (SCAN_PLAN §7), and its
    extension follows the requested output format (Phase 4).
    """
    options = options or {}
    format = options.get("format") or "pdf"
    filename = f"scan-{job_id[:8]}.{SCAN_FILE_EXT[format]}"
    now = _now()
    with _lock:
        _get_conn().execute(
            "INSERT INTO scan_jobs (job_id, filename, size_bytes, status,"
            " created_at, updated_at, format) VALUES (?, ?, 0, ?, ?, ?, ?)",
            (job_id, filename, ScanStatus.QUEUED, now, now, format),
        )
        _get_conn().commit()
        row = _get_conn().execute(
            "SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return _to_job(row)


def get_job(job_id: str) -> ScanJob | None:
    with _lock:
        row = _get_conn().execute(
            "SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return _to_job(row) if row is not None else None


def update_status(
    job_id: str,
    status: str,
    error: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """Move a scan along its lifecycle (used by the scan pipeline).

    error/size_bytes are only written when provided; reaching 'done'
    clears a stale error, since the scan obviously succeeded. Unknown ids
    are a silent no-op — the caller runs on a background thread and must
    never raise.
    """
    with _lock:
        _get_conn().execute(
            "UPDATE scan_jobs SET status = ?, updated_at = ?,"
            " error = CASE WHEN ? = 'done' THEN NULL ELSE COALESCE(?, error) END,"
            " size_bytes = COALESCE(?, size_bytes)"
            " WHERE job_id = ?",
            (status, _now(), status, error, size_bytes, job_id),
        )
        _get_conn().commit()


def cancel_job(job_id: str) -> tuple[bool, str]:
    """Cancel a scan that hasn't reached a terminal state.

    Returns (ok, message). A transfer in flight cannot be interrupted
    mid-COM-call — the pipeline re-checks the status after the transfer
    and discards the result (the same between-stages rule the print
    pipeline has followed since p14).
    """
    with _lock:
        row = _get_conn().execute(
            "SELECT status FROM scan_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return False, "No such scan job."
        status = row["status"]
        if status not in CANCELLABLE:
            return False, (
                f"Scan is '{status}' — only scans that haven't finished can "
                "be cancelled."
            )
        _get_conn().execute(
            "UPDATE scan_jobs SET status = 'cancelled', updated_at = ?"
            " WHERE job_id = ?",
            (_now(), job_id),
        )
        _get_conn().commit()
    return True, "Cancelled."


def recover_interrupted() -> int:
    """Mark scans left queued/scanning by a previous run as failed.

    Called once at startup, after the downloads sweep — their files are
    gone either way, and the error says what happened. Returns how many
    scans were recovered.
    """
    with _lock:
        cursor = _get_conn().execute(
            "UPDATE scan_jobs SET status = 'failed', updated_at = ?, error = ?"
            " WHERE status IN (?, ?)",
            (
                _now(),
                "Service restarted before this scan finished.",
                ScanStatus.QUEUED,
                ScanStatus.SCANNING,
            ),
        )
        _get_conn().commit()
    return cursor.rowcount
