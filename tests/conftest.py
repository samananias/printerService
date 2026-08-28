"""Shared pytest fixtures — conftest.py is auto-loaded before every test.

The fixtures here solve this codebase's four "testing hazards":

1. The job store is a module-level global dict (Section 12) → an autouse
   fixture hands each test a FRESH one, so tests can't leak state into
   each other.
2. Config values are imported BY VALUE into consumer modules
   (`from app.config import MAX_UPLOAD_MB`) → fixtures patch the name where
   it is actually read (e.g. ``app.services.uploads.MAX_UPLOAD_MB``).
   Patching ``app.config`` itself would change nothing.
3. The app's startup sweeps uploads/ of leftover files → tests redirect
   UPLOAD_DIR to a temp dir, so the real uploads/ folder is never touched.
4. Printing runs in a background thread and touches win32print /
   SumatraPDF → tests inject fakes and wait on threading.Event objects
   instead of sleeping.

Rule of the whole suite: tests must pass identically on any machine — no
real printer, no real SumatraPDF, no real .env file is ever consulted.
"""

import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.printer import windows
from app.services import jobs

# The printer name the fakes pretend Windows reports (matching the real
# L3210's queue name keeps the tests readable).
TEST_PRINTER = "EPSON L3210 Series"


# ---------------------------------------------------------------------------
# Isolation fixtures (autouse = applied to every test, no need to request)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_job_store(monkeypatch):
    """Empty in-memory job store for every test (Section 12's dict)."""
    monkeypatch.setattr(jobs, "_jobs", {})


@pytest.fixture(autouse=True)
def tmp_upload_dir(tmp_path, monkeypatch) -> Path:
    """Redirect uploads/ to a temp dir for every test.

    app.services.uploads owns UPLOAD_DIR, and after the upload_path()
    refactor every other consumer goes through uploads.py — so this single
    patch redirects validation storage, the startup sweep, and cancels.
    """
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("app.services.uploads.UPLOAD_DIR", upload_dir)
    return upload_dir


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """FastAPI TestClient with lifespan ENABLED but real logging disabled.

    Entering the context runs the app's lifespan (logging setup + the
    startup sweep) exactly like a real uvicorn start — but against
    tmp_upload_dir, and without creating real log files.
    """
    from app.main import app

    monkeypatch.setattr("app.main.setup_logging", lambda: None)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Fake OS boundaries
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_win32print(monkeypatch) -> types.ModuleType:
    """A stand-in for the pywin32 module, injected into sys.modules.

    app/printer/windows.py imports win32print INSIDE its functions (so the
    app stays bootable on non-Windows machines) — which also means a fake
    module in sys.modules is picked up by that import statement. This is
    what makes the whole printing layer testable on any OS, including the
    Ubuntu CI runner.
    """
    fake = types.ModuleType("win32print")
    fake.PRINTER_ENUM_LOCAL = 0x2
    fake.PRINTER_ENUM_CONNECTIONS = 0x4
    fake.EnumPrinters = lambda flags: [
        ("", "", "Microsoft Print to PDF"),
        ("", "", TEST_PRINTER),
    ]
    fake.GetDefaultPrinter = lambda: TEST_PRINTER
    monkeypatch.setitem(sys.modules, "win32print", fake)
    return fake


class FakePrintResult:
    """Configurable fake for windows.submit_pdf.

    Records the call so tests can assert what the pipeline handed over.
    ``gate`` optionally FREEZES the fake mid-call — a test that sets it can
    observe the transient "queued" state, then release the gate.
    """

    def __init__(self):
        self.called = threading.Event()
        self.gate: threading.Event | None = None
        self.error: Exception | None = None
        self.pdf_path: Path | None = None
        self.printer_name: str | None = None

    def __call__(self, pdf_path, printer_name=None):
        self.pdf_path = pdf_path
        self.printer_name = printer_name
        self.called.set()
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.error is not None:
            raise self.error
        return "sumatrapdf", TEST_PRINTER


@pytest.fixture
def mock_print(monkeypatch) -> FakePrintResult:
    """Replace windows.submit_pdf so no test can ever reach a real printer
    (on a Windows dev box the real one would print actual paper!)."""
    fake = FakePrintResult()
    monkeypatch.setattr(windows, "submit_pdf", fake)
    return fake


@pytest.fixture
def wait_until():
    """Poll a predicate until it is truthy, with a deadline.

    The generic twin of wait_for_status: useful for watching side effects
    the pipeline performs slightly AFTER a status changes (e.g. the temp
    file is unlinked just after the job is marked done).
    """

    def _wait(predicate, timeout: float = 5.0, message: str = "condition never held"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError(f"{message} (still false after {timeout}s)")

    return _wait


@pytest.fixture
def wait_for_status():
    """Poll the job store until the job reaches one of the given statuses.

    The printing thread moves the status ASYNCHRONOUSLY, and even the fakes
    are fast enough that a test can read the store mid-update — so instead
    of asserting immediately (a race) or sleeping a fixed time (slow AND a
    race), tests poll with a deadline. Raises if the status never arrives.
    """

    def _wait(job_id: str, *statuses: str, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = jobs.get_job(job_id)
            if job is not None and job.status in statuses:
                return job
            time.sleep(0.01)
        job = jobs.get_job(job_id)
        last = job.status if job is not None else "<no job>"
        raise AssertionError(
            f"job {job_id!r} never reached {statuses} within {timeout}s "
            f"(last state: {last})"
        )

    return _wait


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def make_test_pdf_bytes() -> bytes:
    """A minimal but structurally valid one-page PDF, built from scratch.

    Same construction as spike_print_test.py's make_test_pdf(), minus the
    file writing — validation only inspects the magic bytes, but a real
    PDF keeps the fixtures honest and is reusable if a future test ever
    needs a genuine renderable document.
    """
    content = b"BT /F1 24 Tf 72 720 Td (printer service test page) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
        + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_position = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    return bytes(out)


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_test_pdf_bytes()
