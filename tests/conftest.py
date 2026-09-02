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

import itertools
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.printer import windows
from app.services import jobs, scan_jobs

# The printer name the fakes pretend Windows reports (matching the real
# L3210's queue name keeps the tests readable).
TEST_PRINTER = "EPSON L3210 Series"


# ---------------------------------------------------------------------------
# Isolation fixtures (autouse = applied to every test, no need to request)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_job_store(tmp_path, monkeypatch):
    """A fresh SQLite job store for every test (Section 12 → p14).

    jobs.py keeps a module-level connection; pointing _db_path at a temp
    file and dropping the cached connection makes every test start from an
    empty database — the equivalent of the old fresh dict.
    """
    monkeypatch.setattr(jobs, "_db_path", tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(jobs, "_conn", None)
    # The scan store shares the DB FILE but owns its own connection —
    # patch both halves (SCAN_PLAN §0: scan never touches print's store).
    monkeypatch.setattr(scan_jobs, "_db_path", tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(scan_jobs, "_conn", None)


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


@pytest.fixture(autouse=True)
def tmp_download_dir(tmp_path, monkeypatch) -> Path:
    """Redirect downloads/ to a temp dir for every test — scan artifacts
    (raw PNG, finished PDF) and the startup sweep, same rule as
    tmp_upload_dir (SCAN_PLAN §5: downloads/ is uploads/' twin)."""
    download_dir = tmp_path / "downloads"
    # Tests write into it directly — the dir must exist up front.
    download_dir.mkdir()
    monkeypatch.setattr("app.services.downloads.DOWNLOAD_DIR", download_dir)
    return download_dir


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

    # Spooler-queue surface for the p14 cancel purge. Tests populate
    # _spooler_jobs with level-1 dicts (JobId, pDocument) and read
    # setjob_calls to verify what was purged.
    fake.JOB_CONTROL_DELETE = 3
    fake._spooler_jobs = []
    fake.setjob_calls = []
    fake.OpenPrinter = lambda name: f"handle:{name}"
    fake.ClosePrinter = lambda handle: None
    fake.EnumJobs = lambda handle, first, count, level: list(fake._spooler_jobs)

    def _set_job(handle, job_id, level, info, command):
        fake.setjob_calls.append((handle, job_id, command))

    fake.SetJob = _set_job

    # Level-2 printer info for the p15 readiness check: a healthy printer
    # by default (Status 0, no WORK_OFFLINE attribute). Tests override.
    fake.GetPrinter = lambda handle, level: {"Status": 0, "Attributes": 0}

    monkeypatch.setitem(sys.modules, "win32print", fake)
    return fake


@pytest.fixture
def fake_win32com(monkeypatch):
    """A stand-in for the WIA automation layer, injected into sys.modules.

    app/scanner/windows.py imports win32com.client INSIDE its functions —
    the same trick app/printer/windows.py uses for win32print — so a fake
    module is picked up by that import, making scanner detection testable
    on any OS (the Ubuntu CI runner has no real pywin32 at all).

    BOTH "win32com" and "win32com.client" are injected: a dotted import
    imports the parent package first, so both names must exist.

    Usage:
        fake_win32com.add_device()                        # the L3210 by default
        fake_win32com.add_device(name="Cam", wia_type=2)  # a camera, not a scanner
        fake_win32com.fail_dispatch(RuntimeError("..."))  # WIA itself blows up
    """
    client = types.ModuleType("win32com.client")
    package = types.ModuleType("win32com")
    package.client = client

    sequence = itertools.count(1)
    state: dict = {"fail": None, "settings": {}}

    class _FakeProp:
        """A WIA item property whose Value can be set — and every set is
        recorded in state['settings'], so tests can assert the scanner was
        actually asked for the requested dpi / color mode (Phase 4)."""

        __slots__ = ("_value", "key")

        def __init__(self, value, key):
            self._value = value
            self.key = key

        @property
        def Value(self):
            return self._value

        @Value.setter
        def Value(self, v):
            self._value = v
            state["settings"][self.key] = v

    class FakeDeviceInfos:
        def __init__(self):
            self.items = []

        @property
        def Count(self):
            return len(self.items)

        def Item(self, index):
            if not 1 <= index <= len(self.items):
                raise IndexError(f"WIA index {index} out of range")
            return self.items[index - 1]  # 1-based, like the real WIA

    infos = FakeDeviceInfos()
    manager = types.SimpleNamespace(DeviceInfos=infos)

    def dispatch(prog_id):
        if state["fail"] is not None:
            raise state["fail"]
        if prog_id != "WIA.DeviceManager":
            raise ValueError(f"unexpected ProgID: {prog_id!r}")
        return manager

    client.Dispatch = dispatch

    def add_device(
        name: str = "EPSON L3210 Series",
        wia_type: int = 1,
        device_id=None,
        no_name: bool = False,
        transfer_error: Exception | None = None,
        entered: threading.Event | None = None,
        gate: threading.Event | None = None,
        corrupt_png: bool = False,
    ):
        """Add one WIA DeviceInfo.

        no_name=True simulates a device whose Properties("Name") read
        fails (the _display_name fallback path).
        transfer_error: item.Transfer() raises it (WIA trouble mid-scan).
        entered/gate: a SLOW scanner — Transfer() sets entered, then waits
        on gate before "saving" — letting a test cancel mid-transfer.
        corrupt_png: SaveFile writes garbage bytes, so the REAL
        ImageProcessor refuses the image (wrap-failure path).
        """

        def properties(prop_name):
            if no_name and str(prop_name) in ("Name", "Item Name"):
                # Preserve the detection fallback path: a device whose name
                # read fails. Best-effort option-setting (resolution /
                # intent) is still allowed on such a device.
                raise RuntimeError(f"no {prop_name} property")
            key = str(prop_name)
            if key in ("Name", "Item Name"):
                value = name
            else:
                value = state["settings"].get(key)
            return _FakeProp(value, key)

        def transfer(_format_id):
            if entered is not None:
                entered.set()
            if transfer_error is not None:
                raise transfer_error
            if gate is not None:
                gate.wait(timeout=10)

            def save_file(path):
                if corrupt_png:
                    # SaveFile hands a str path (the production call passes
                    # str(dest)) — write garbage the ImageProcessor refuses.
                    Path(path).write_bytes(b"not an image at all")
                    return
                # A tiny REAL PNG — the pipeline wraps it with the real
                # ImageProcessor, which needs genuine image bytes.
                from PIL import Image

                Image.new("RGB", (16, 12), "white").save(path, "PNG")

            return types.SimpleNamespace(SaveFile=save_file)

        # The transferable flatbed item, reachable exactly the way the
        # production _open_flatbed_item() walks WIA:
        # DeviceInfos -> info.Connect() -> device.Items -> Item(1).
        item = types.SimpleNamespace(Transfer=transfer, Properties=properties)
        items = types.SimpleNamespace(
            Count=1,
            Item=lambda index: item
            if index == 1
            else (_ for _ in ()).throw(IndexError(index)),
        )

        def connect():
            return types.SimpleNamespace(Items=items)

        info = types.SimpleNamespace(
            Type=wia_type,
            DeviceID=device_id or f"wia-device-{next(sequence)}",
            Properties=properties,
            Transfer=transfer,
            Connect=connect,
        )
        infos.items.append(info)
        return info

    def fail_dispatch(exc: Exception):
        state["fail"] = exc

    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    return types.SimpleNamespace(
        infos=infos,
        add_device=add_device,
        fail_dispatch=fail_dispatch,
        settings=state["settings"],
    )


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
        self.options: dict | None = None

    def __call__(self, pdf_path, printer_name=None, options=None):
        self.pdf_path = pdf_path
        self.printer_name = printer_name
        self.options = options
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


@pytest.fixture
def wait_for_scan_status():
    """Poll the SCAN store until a scan reaches one of the statuses —
    the twin of wait_for_status for the separate scan store (SCAN_PLAN
    §4: scan jobs live in their own table, so they get their own waiter)."""

    def _wait(job_id: str, *statuses: str, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = scan_jobs.get_job(job_id)
            if job is not None and job.status in statuses:
                return job
            time.sleep(0.01)
        job = scan_jobs.get_job(job_id)
        last = job.status if job is not None else "<no job>"
        raise AssertionError(
            f"scan {job_id!r} never reached {statuses} within {timeout}s "
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
