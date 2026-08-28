"""Unit tests for the print pipeline (app/services/pipeline.py).

start_job() hands work to a daemon thread; the fakes signal a
threading.Event so each test waits deterministically for that thread
instead of sleeping. This is where the documented lifecycle lives:

    received → queued → done   (file deleted)
                       ↘ failed (file kept for diagnosis)
"""

import threading

import pytest

from app.models.printing import JobStatus
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
    def test_job_is_queued_while_the_print_thread_is_still_running(
        self, job_with_pdf, mock_print, wait_for_status
    ):
        # The fake is so fast the thread could finish before this test even
        # reads the store — so freeze it with a gate to observe "queued",
        # the state the phone's 201 response reflects.
        gate = threading.Event()
        mock_print.gate = gate

        pipeline.start_job("job-1", job_with_pdf)

        assert mock_print.called.wait(timeout=5)
        assert jobs.get_job("job-1").status == JobStatus.QUEUED

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

        assert mock_print.pdf_path == job_with_pdf
        # printer_name=None means "let windows.py resolve PRINTER_NAME/default".
        assert mock_print.printer_name is None
