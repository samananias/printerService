"""Unit tests for the print pipeline (app/services/pipeline.py).

start_job() hands work to a daemon thread; the fakes signal a
threading.Event so each test waits deterministically for that thread
instead of sleeping. This is where the documented lifecycle lives:

    received → queued → converting → printing → done   (files deleted)
                                              ↘ failed (files kept)

Since p10 the pipeline has a conversion stage between upload and print:
the processor turns the source file into the service's one print format
(a PDF). Phase 1 registers only the PDF pass-through, so the PDF path is
a no-op conversion — the office/image/text stages arrive in later phases
(docs/MULTI_FORMAT_PLAN.md §10).
"""

import threading

import pytest

from app.models.printing import JobStatus
from app.processors.base import ConversionError
from app.services import jobs, pipeline

TEST_PRINTER = "EPSON L3210 Series"


@pytest.fixture
def job_with_pdf(tmp_upload_dir):
    """A registered job whose upload really exists on disk (in the temp dir)."""
    tmp_upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_upload_dir / "job-1.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    jobs.create_job("job-1", "file.pdf", 13, pdf_path)
    return pdf_path


class TestStartJob:
    def test_job_is_in_printing_state_while_the_print_thread_is_running(
        self, job_with_pdf, mock_print, wait_for_status
    ):
        # The fake is frozen mid-print so the test can observe the transient
        # "printing" state. The phone's 201 still says "queued" — this is
        # what polling sees on the way to done.
        gate = threading.Event()
        mock_print.gate = gate

        pipeline.start_job("job-1", job_with_pdf)

        assert mock_print.called.wait(timeout=5)
        assert jobs.get_job("job-1").status == JobStatus.PRINTING

        gate.set()
        wait_for_status("job-1", JobStatus.DONE)  # completes once released

    def test_done_records_printer_and_deletes_the_file(
        self, job_with_pdf, mock_print, wait_for_status, wait_until
    ):
        pipeline.start_job("job-1", job_with_pdf)

        job = wait_for_status("job-1", JobStatus.DONE)
        assert job.printer == TEST_PRINTER

        # DONE is recorded slightly BEFORE the temp file is unlinked, so
        # wait for the deletion itself rather than asserting in the gap.
        wait_until(
            lambda: not job_with_pdf.exists(),
            message="printed job's temp file should be deleted",
        )

    def test_failure_records_error_and_keeps_the_file(
        self, job_with_pdf, mock_print, wait_for_status
    ):
        mock_print.error = RuntimeError("SumatraPDF failed (exit 1): printer offline")

        pipeline.start_job("job-1", job_with_pdf)

        job = wait_for_status("job-1", JobStatus.FAILED)
        assert "printer offline" in job.error
        assert job_with_pdf.exists()  # kept for diagnosis; startup sweeps later

    def test_hands_the_right_file_to_the_printer(
        self, job_with_pdf, mock_print, wait_for_status
    ):
        pipeline.start_job("job-1", job_with_pdf)

        wait_for_status("job-1", JobStatus.DONE)

        # The PDF processor is a pass-through: Sumatra receives the upload
        # exactly as stored — same contract spike T4 proved on real paper.
        assert mock_print.pdf_path == job_with_pdf
        # printer_name=None means "let windows.py resolve PRINTER_NAME/default".
        assert mock_print.printer_name is None


class TestConversionStage:
    """The conversion stage between upload and print (p10 groundwork)."""

    def test_conversion_failure_marks_failed_and_never_prints(
        self, job_with_pdf, mock_print, monkeypatch, wait_for_status
    ):
        class FailingProcessor:
            def process(self, src, out_dir):
                raise ConversionError("LibreOffice crashed mid-conversion")

        monkeypatch.setattr(pipeline, "for_category", lambda category: FailingProcessor())

        pipeline.start_job("job-1", job_with_pdf, category="office")

        job = wait_for_status("job-1", JobStatus.FAILED)
        assert "crashed" in job.error
        assert job_with_pdf.exists()  # kept for diagnosis
        assert mock_print.called.is_set() is False  # nothing reached the printer

    def test_conversions_run_one_at_a_time(
        self, tmp_upload_dir, mock_print, monkeypatch, wait_for_status, wait_until
    ):
        # The old-PC guard: with a ≤4 GB machine and a future heavyweight
        # converter (LibreOffice), two jobs must never convert at once.
        class SlowProcessor:
            def __init__(self):
                self.in_process = 0
                self.max_in_process = 0
                self.release = threading.Event()

            def process(self, src, out_dir):
                self.in_process += 1
                self.max_in_process = max(self.max_in_process, self.in_process)
                self.release.wait(timeout=5)
                self.in_process -= 1
                return src

        slow = SlowProcessor()
        monkeypatch.setattr(pipeline, "for_category", lambda category: slow)

        tmp_upload_dir.mkdir(parents=True, exist_ok=True)
        for number in ("1", "2"):
            path = tmp_upload_dir / f"job-{number}.pdf"
            path.write_bytes(b"%PDF-1.4 test")
            jobs.create_job(f"job-{number}", "file.pdf", 13, path, format="office")
            pipeline.start_job(f"job-{number}", path, category="office")

        wait_until(lambda: slow.in_process >= 1, message="first conversion never started")

        slow.release.set()
        wait_for_status("job-1", JobStatus.DONE)
        wait_for_status("job-2", JobStatus.DONE)

        assert slow.max_in_process == 1  # the second never overlapped the first


class TestCancellation:
    """p14: a cancel wins over the next print stage, wherever it lands."""

    @pytest.fixture
    def gated_processor(self, monkeypatch):
        """A converter that parks mid-conversion until its test releases it."""

        class GatedProcessor:
            def __init__(self):
                self.entered = threading.Event()
                self.release = threading.Event()

            def process(self, src, out_dir):
                self.entered.set()
                self.release.wait(timeout=5)
                return src

        gated = GatedProcessor()
        monkeypatch.setattr(pipeline, "for_category", lambda category: gated)
        return gated

    def test_cancel_during_conversion_never_prints(
        self, job_with_pdf, mock_print, gated_processor, wait_until
    ):
        pipeline.start_job("job-1", job_with_pdf, category="office")
        assert gated_processor.entered.wait(timeout=5)

        ok, _ = jobs.cancel_job("job-1")  # while the conversion is parked
        assert ok is True

        gated_processor.release.set()
        wait_until(
            lambda: not job_with_pdf.exists(),
            message="cancelled job's files should be cleaned up",
        )

        assert mock_print.called.is_set() is False  # nothing reached the printer
        assert jobs.get_job("job-1").status == JobStatus.CANCELLED

    def test_cancel_while_printing_keeps_cancelled_after_submit(
        self, job_with_pdf, mock_print, tmp_upload_dir, wait_for_status, wait_until
    ):
        gate = threading.Event()
        mock_print.gate = gate
        pipeline.start_job("job-1", job_with_pdf)
        wait_for_status("job-1", JobStatus.PRINTING)

        ok, _ = jobs.cancel_job("job-1")  # the spooler purge runs in the API
        assert ok is True

        gate.set()
        wait_until(
            lambda: not job_with_pdf.exists(),
            message="cancelled job's files should be cleaned up",
        )

        # Sumatra was handed the file (paper may come out — documented), but
        # the pipeline must NOT mark the cancelled job done.
        assert mock_print.called.is_set() is True
        assert jobs.get_job("job-1").status == JobStatus.CANCELLED

    def test_cancelled_before_the_thread_starts_is_never_processed(
        self, job_with_pdf, mock_print
    ):
        jobs.cancel_job("job-1")  # cancel between create and start
        pipeline.start_job("job-1", job_with_pdf)

        import time

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not mock_print.called.is_set():
            time.sleep(0.01)

        assert mock_print.called.is_set() is False
        assert jobs.get_job("job-1").status == JobStatus.CANCELLED
