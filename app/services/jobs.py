"""Job tracking (Phase 7's in-memory dict → Phase 5's SQLite store).

SOURCE_OF_TRUTH Section 12 prescribed a plain dict for v1 and named the
upgrade path for when persistence started to matter. Multi-format office
jobs (tens of seconds each) crossed that line: losing a queued job to a
restart now costs real time, and "retry failed" needs the uploaded file's
location to outlive the request.

The function surface is the same as the dict version — nothing else in
the app changed — now backed by one SQLite file (config: JOB_DB_PATH,
default `logs/jobs.sqlite3`):

    jobs table: job_id (PK), filename, size_bytes, status, created_at,
                updated_at, printer, error, format, source_path, category

The threading.Lock stays (RLock now): uvicorn's thread pool and the print
threads mutate the store concurrently, and the shared sqlite3 connection
must not be used from two threads at once.

Startup recovery (recover_interrupted, called from main's lifespan) flips
jobs left in active states by a crashed run to failed — their uploads are
already gone (the startup sweep deletes everything in uploads/), so they
can't be retried; the error message says so.

Cancellation rules (p14): a job may be cancelled while received, queued,
converting or printing. Printing-cancels are best-effort — the spooler
purge (app/printer/windows.py) removes queued Windows jobs, but paper
that already reached the printer cannot be recalled; the pipeline checks
the cancelled status after each stage and never marks a cancelled job
done.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import JOB_DB_PATH
from app.models.printing import JobStatus, PrintJob

# The states a cancel request may interrupt (p14). done/failed/cancelled
# are terminal — cancelling those is refused with the current state.
CANCELLABLE = frozenset(
    {JobStatus.RECEIVED, JobStatus.QUEUED, JobStatus.CONVERTING, JobStatus.PRINTING}
)

_lock = threading.RLock()
_db_path = Path(JOB_DB_PATH)
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    printer     TEXT,
    error       TEXT,
    format      TEXT,
    source_path TEXT,
    category    TEXT
)
"""


def _get_conn() -> sqlite3.Connection:
    """The shared connection, created (with schema) on first use.

    check_same_thread=False: access is serialized by _lock instead, which
    also guards the check-then-modify sequences the dict version needed.
    """
    global _conn
    if _conn is None:
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(_db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(_SCHEMA)
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_job(row: sqlite3.Row) -> PrintJob:
    return PrintJob(
        job_id=row["job_id"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        printer=row["printer"],
        error=row["error"],
        format=row["format"],
    )


def create_job(
    job_id: str,
    filename: str,
    size_bytes: int,
    path: Path,
    format: str | None = None,
) -> PrintJob:
    """Register a freshly uploaded file as a tracked job.

    `format` is the detected category from upload validation; the file's
    location and category are stored alongside it so a failed job can be
    retried (p14).
    """
    now = _now()
    with _lock:
        _get_conn().execute(
            "INSERT INTO jobs (job_id, filename, size_bytes, status, created_at,"
            " updated_at, format, source_path, category)"
            " VALUES (?, ?, ?, 'received', ?, ?, ?, ?, ?)",
            (job_id, filename, size_bytes, now, now, format, str(path), format),
        )
        _get_conn().commit()
        row = _get_conn().execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return _to_job(row)


def get_job(job_id: str) -> PrintJob | None:
    with _lock:
        row = _get_conn().execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return _to_job(row) if row is not None else None


def list_jobs() -> list[PrintJob]:
    """All jobs, oldest first."""
    with _lock:
        rows = _get_conn().execute(
            "SELECT * FROM jobs ORDER BY created_at, rowid"
        ).fetchall()
    return [_to_job(row) for row in rows]


def update_status(
    job_id: str,
    status: str,
    error: str | None = None,
    printer: str | None = None,
) -> None:
    """Move a job along its lifecycle (used by the printing pipeline).

    error/printer are only written when provided; reaching 'done' clears a
    stale error, since the job obviously succeeded. Unknown ids are a
    silent no-op — callers run on background threads and must never raise.
    """
    with _lock:
        _get_conn().execute(
            "UPDATE jobs SET status = ?, updated_at = ?,"
            " error = CASE WHEN ? = 'done' THEN NULL ELSE COALESCE(?, error) END,"
            " printer = COALESCE(?, printer)"
            " WHERE job_id = ?",
            (status, _now(), status, error, printer, job_id),
        )
        _get_conn().commit()


def cancel_job(job_id: str) -> tuple[bool, str]:
    """Cancel a job that hasn't reached a terminal state.

    Returns (ok, message). Cancellable states (p14): received/queued
    (nothing happened yet), converting (the pipeline checks the status
    between stages and abandons the job), printing (best-effort — the
    caller also purges the Windows spooler queue; paper that already
    fed into the printer cannot be recalled).
    """
    with _lock:
        row = _get_conn().execute(
            "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return False, "No such job."
        status = row["status"]
        if status not in CANCELLABLE:
            return False, (
                f"Job is '{status}' — only jobs that haven't finished can be "
                "cancelled."
            )
        _get_conn().execute(
            "UPDATE jobs SET status = 'cancelled', updated_at = ? WHERE job_id = ?",
            (_now(), job_id),
        )
        _get_conn().commit()
    return True, "Cancelled."


def get_source(job_id: str) -> tuple[Path, str] | None:
    """The (file, category) a job was created from — retry's raw material."""
    with _lock:
        row = _get_conn().execute(
            "SELECT source_path, category FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None or row["source_path"] is None:
        return None
    return Path(row["source_path"]), row["category"] or "pdf"


def reset_for_retry(job_id: str) -> bool:
    """Move a FAILED job back to received, clearing its error.

    Only failed jobs qualify (a failed job's files are kept for exactly
    this purpose); returns False for anything else.
    """
    with _lock:
        cursor = _get_conn().execute(
            "UPDATE jobs SET status = 'received', error = NULL, updated_at = ?"
            " WHERE job_id = ? AND status = 'failed'",
            (_now(), job_id),
        )
        _get_conn().commit()
    return cursor.rowcount > 0


def recover_interrupted() -> int:
    """Mark jobs left in active states by a previous run as failed.

    Called once at startup. Their uploaded files are already gone (the
    startup sweep clears uploads/), so retrying is impossible — the error
    says what happened. Returns how many jobs were recovered.
    """
    active = (JobStatus.RECEIVED, JobStatus.QUEUED, JobStatus.CONVERTING, JobStatus.PRINTING)
    with _lock:
        cursor = _get_conn().execute(
            "UPDATE jobs SET status = 'failed', updated_at = ?, error = ?"
            " WHERE status IN (?, ?, ?, ?)",
            (_now(), "Service restarted before this job finished.", *active),
        )
        _get_conn().commit()
    return cursor.rowcount
