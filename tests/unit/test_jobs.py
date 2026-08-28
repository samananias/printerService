"""Unit tests for the in-memory job store (app/services/jobs.py).

The store is Section 12's deliberate v1 design: a dict behind a threading
lock, no database. The conftest gives every test a fresh store (autouse
fresh_job_store fixture), so these tests are isolated by construction.
"""

import threading
from pathlib import Path

from app.models.printing import JobStatus
from app.services import jobs


def make_job(job_id: str = "job-1"):
    return jobs.create_job(job_id, "file.pdf", 123, Path("uploads") / f"{job_id}.pdf")


class TestCreateAndGet:
    def test_new_job_starts_received(self):
        job = make_job()
        assert job.status == JobStatus.RECEIVED
        assert job.job_id == "job-1"
        assert job.filename == "file.pdf"
        assert job.size_bytes == 123
        assert job.error is None
        assert job.printer is None

    def test_created_and_updated_timestamps_are_set(self):
        job = make_job()
        assert job.created_at is not None
        assert job.updated_at is not None

    def test_unknown_id_returns_none(self):
        assert jobs.get_job("ghost") is None


class TestListJobs:
    def test_empty_store_lists_nothing(self):
        assert jobs.list_jobs() == []

    def test_lists_jobs_oldest_first(self):
        make_job("first")
        make_job("second")
        make_job("third")
        assert [j.job_id for j in jobs.list_jobs()] == ["first", "second", "third"]


class TestUpdateStatus:
    def test_moves_job_forward(self):
        make_job()
        jobs.update_status("job-1", JobStatus.QUEUED)
        assert jobs.get_job("job-1").status == JobStatus.QUEUED

    def test_done_records_printer_and_clears_stale_error(self):
        make_job()
        jobs.update_status("job-1", JobStatus.FAILED, error="printer offline")
        jobs.update_status("job-1", JobStatus.DONE, printer="EPSON L3210 Series")

        job = jobs.get_job("job-1")
        assert job.status == JobStatus.DONE
        assert job.printer == "EPSON L3210 Series"
        assert job.error is None  # a done job obviously succeeded

    def test_failed_records_error_message(self):
        make_job()
        jobs.update_status("job-1", JobStatus.FAILED, error="SumatraPDF not found")
        assert jobs.get_job("job-1").error == "SumatraPDF not found"

    def test_unknown_id_is_a_silent_no_op(self):
        # update_status is called from a background thread — it must never
        # raise, even for a job that has vanished (e.g. after a store reset).
        jobs.update_status("ghost", JobStatus.DONE)  # no exception
        assert jobs.get_job("ghost") is None


class TestCancelJob:
    def test_received_job_can_be_cancelled(self):
        make_job()
        ok, message = jobs.cancel_job("job-1")
        assert ok is True
        assert jobs.get_job("job-1").status == JobStatus.CANCELLED

    def test_already_cancelled_job_cannot_be_cancelled_again(self):
        make_job()
        jobs.cancel_job("job-1")
        ok, _ = jobs.cancel_job("job-1")
        assert ok is False

    def test_printed_job_cannot_be_cancelled(self):
        make_job()
        jobs.update_status("job-1", JobStatus.DONE, printer="EPSON L3210 Series")
        ok, message = jobs.cancel_job("job-1")
        assert ok is False
        assert "done" in message  # the refusal explains the current state
        assert jobs.get_job("job-1").status == JobStatus.DONE

    def test_unknown_job_cannot_be_cancelled(self):
        ok, message = jobs.cancel_job("ghost")
        assert ok is False
        assert "No such job" in message


class TestConcurrency:
    def test_simultaneous_creates_from_many_threads_do_not_lose_jobs(self):
        # The lock exists because uvicorn runs sync endpoints in a thread
        # pool — this smoke test proves the lock actually protects the dict.
        def worker(worker_id: int):
            for i in range(5):
                make_job(f"job-{worker_id}-{i}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(jobs.list_jobs()) == 40
