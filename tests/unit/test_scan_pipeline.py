"""Scan pipeline tests (docs/SCAN_PLAN.md §9): the WIA boundary is faked,
the ImageProcessor and the store are REAL — no scanner is touched. Same
bounded-polling style as the print pipeline tests."""

import threading

from app.models.scanning import ScanStatus
from app.services import downloads, scan_jobs
from app.services.scan_pipeline import start_scan


def _com_error(scode: int) -> Exception:
    """A pywin32-shaped COM error: args[2][5] carries the HRESULT (exactly
    the shape spike S4's SaveFile collision produced).

    Deliberately NOT a RuntimeError: pywintypes.com_error isn't one either,
    and scan_flatbed only re-raises RuntimeErrors as already-translated
    (its own "scanner was not found" message)."""
    class FakeComError(Exception):
        pass

    exc = FakeComError()
    exc.args = (
        -2147352567,
        "Exception occurred.",
        (0, "WIA.Device.1", "device error", None, 0, scode),
        None,
    )
    return exc


class TestHappyPath:
    def test_scan_job_completes_with_a_real_pdf(
        self, fake_win32com, wait_for_scan_status, tmp_download_dir
    ):
        fake_win32com.add_device()
        scan_jobs.create_job("scanok")
        start_scan("scanok")

        job = wait_for_scan_status("scanok", ScanStatus.DONE)
        pdf = downloads.result_path("scanok")
        assert pdf.is_file()
        assert pdf.read_bytes()[:5] == b"%PDF-"  # wrapped by ImageProcessor
        assert job.size_bytes > 0
        assert job.filename == "scan-scanok.pdf"
        # The raw PNG is gone; only the deliverable remains (§5 step 3).
        assert not downloads.working_path("scanok").exists()
        assert [p.name for p in tmp_download_dir.iterdir()] == [pdf.name]

    def test_scanning_status_is_visible_while_the_thread_runs(
        self, fake_win32com, wait_for_scan_status
    ):
        entered = threading.Event()
        gate = threading.Event()
        fake_win32com.add_device(entered=entered, gate=gate)
        scan_jobs.create_job("slowscan")
        start_scan("slowscan")

        assert entered.wait(timeout=5)  # transfer in flight
        job = wait_for_scan_status("slowscan", ScanStatus.SCANNING)
        assert job.status == "scanning"
        gate.set()
        wait_for_scan_status("slowscan", ScanStatus.DONE)


class TestOutputFormats:
    def test_png_output_keeps_the_raw_png_as_deliverable(
        self, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device()
        scan_jobs.create_job("pngout", {"format": "png"})
        start_scan("pngout", {"format": "png"})

        job = wait_for_scan_status("pngout", ScanStatus.DONE)
        assert job.filename == "scan-pngout.png"
        out = downloads.result_path("pngout", "png")
        assert out.is_file()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG magic
        assert job.size_bytes > 0

    def test_jpeg_output_is_a_real_jpeg(
        self, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device()
        scan_jobs.create_job("jpgout", {"format": "jpeg"})
        start_scan("jpgout", {"format": "jpeg"})

        wait_for_scan_status("jpgout", ScanStatus.DONE)
        out = downloads.result_path("jpgout", "jpg")
        assert out.read_bytes()[:2] == b"\xff\xd8"  # JPEG SOI marker
        assert not downloads.working_path("jpgout").exists()  # PNG was interim

    def test_scan_options_reach_the_scanner(
        self, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device()
        scan_jobs.create_job("opts1", {"dpi": 300, "color_mode": "greyscale"})
        start_scan("opts1", {"dpi": 300, "color_mode": "greyscale"})

        wait_for_scan_status("opts1", ScanStatus.DONE)
        # The fake WIA item recorded what it was asked for (Phase 4).
        assert fake_win32com.settings.get("Horizontal Resolution") == 300
        assert fake_win32com.settings.get("Vertical Resolution") == 300
        assert fake_win32com.settings.get("Current Intent") == 2  # grayscale


class TestFailures:
    def test_com_error_is_translated_to_a_human_message(
        self, fake_win32com, wait_for_scan_status
    ):
        # WIA_ERROR_BUSY (0x80210005), signed 32-bit like pywin32 reports.
        fake_win32com.add_device(transfer_error=_com_error(0x80210005 - 2**32))
        scan_jobs.create_job("busy1")
        start_scan("busy1")

        job = wait_for_scan_status("busy1", ScanStatus.FAILED)
        assert "busy" in job.error.lower()

    def test_plain_error_falls_back_to_its_text(
        self, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device(transfer_error=RuntimeError("glass empty"))
        scan_jobs.create_job("plain1")
        start_scan("plain1")

        job = wait_for_scan_status("plain1", ScanStatus.FAILED)
        assert "glass empty" in job.error

    def test_vanished_scanner_fails_with_a_readable_error(
        self, fake_win32com, wait_for_scan_status
    ):
        # Detection said "yes" at accept time, but by transfer time WIA
        # sees no scanner at all (USB yanked) — a FAILED job, not a 500.
        scan_jobs.create_job("gone1")
        start_scan("gone1")

        job = wait_for_scan_status("gone1", ScanStatus.FAILED)
        assert "not found" in job.error

    def test_failed_scan_keeps_its_raw_png_for_diagnosis(
        self, fake_win32com, wait_for_scan_status
    ):
        # The PNG lands but is garbage, so the REAL ImageProcessor refuses
        # it — the job fails and the raw PNG stays (startup sweep cleans up
        # eventually; there is no retry in Phase 2, the phone scans again).
        fake_win32com.add_device(corrupt_png=True)

        scan_jobs.create_job("keep1")
        start_scan("keep1")
        wait_for_scan_status("keep1", ScanStatus.FAILED)
        assert downloads.working_path("keep1").is_file()
        assert not downloads.result_path("keep1").exists()


class TestCancellation:
    def test_cancelled_before_start_never_scans(self, fake_win32com):
        entered = threading.Event()
        fake_win32com.add_device(entered=entered)
        scan_jobs.create_job("early1")
        scan_jobs.cancel_job("early1")

        start_scan("early1")  # must not resurrect the cancelled job

        assert scan_jobs.get_job("early1").status == ScanStatus.CANCELLED
        assert not entered.is_set()  # no transfer was ever attempted

    def test_cancel_during_transfer_discards_the_result(
        self, fake_win32com, wait_for_scan_status, wait_until
    ):
        entered = threading.Event()
        gate = threading.Event()
        fake_win32com.add_device(entered=entered, gate=gate)
        scan_jobs.create_job("midcan")
        start_scan("midcan")

        assert entered.wait(timeout=5)  # transfer in flight
        ok, _ = scan_jobs.cancel_job("midcan")
        assert ok
        gate.set()  # the scanner finishes — but the job is already cancelled

        job = wait_for_scan_status("midcan", ScanStatus.CANCELLED)
        wait_until(
            lambda: downloads.job_files("midcan") == [],
            message="cancel cleanup never removed the scan files",
        )
        # A cancelled scan is never marked done, even though the image arrived.
        assert job.status == ScanStatus.CANCELLED


class TestStartScanGuards:
    def test_start_scan_is_safe_for_unknown_ids(self):
        # update_status is a no-op for unknown ids; the thread dies quietly.
        start_scan("ghost")
        assert scan_jobs.get_job("ghost") is None
