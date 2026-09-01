"""Unit tests for the scan job store (docs/SCAN_PLAN.md §5).

The store is deliberately separate from the print store (SCAN_PLAN §4) —
these tests also verify the two never share a connection: fresh_job_store
patches both, and every operation here only ever touches scan_jobs.
"""

from app.services import scan_jobs


class TestCreateAndGet:
    def test_create_starts_queued_with_a_download_name(self):
        job = scan_jobs.create_job("abcdef1234567890")
        assert job.status == "queued"
        assert job.size_bytes == 0
        assert job.filename == "scan-abcdef12.pdf"  # server-generated (§7)
        assert scan_jobs.get_job("abcdef1234567890").status == "queued"

    def test_unknown_job_is_none(self):
        assert scan_jobs.get_job("nope") is None


class TestUpdateStatus:
    def test_moves_through_the_lifecycle(self):
        scan_jobs.create_job("job1")
        scan_jobs.update_status("job1", "scanning")
        assert scan_jobs.get_job("job1").status == "scanning"
        scan_jobs.update_status("job1", "done", size_bytes=1234)
        job = scan_jobs.get_job("job1")
        assert job.status == "done"
        assert job.size_bytes == 1234
        assert job.error is None

    def test_error_is_recorded_and_cleared_by_done(self):
        scan_jobs.create_job("job2")
        scan_jobs.update_status("job2", "failed", error="glass empty")
        assert scan_jobs.get_job("job2").error == "glass empty"
        scan_jobs.update_status("job2", "done")
        assert scan_jobs.get_job("job2").error is None

    def test_existing_error_sticks_when_none_provided(self):
        scan_jobs.create_job("job3")
        scan_jobs.update_status("job3", "failed", error="busy")
        scan_jobs.update_status("job3", "failed")  # no new error given
        assert scan_jobs.get_job("job3").error == "busy"

    def test_unknown_id_is_a_silent_noop(self):
        # Background threads call this — it must never raise.
        scan_jobs.update_status("ghost", "done")


class TestCancel:
    def test_queued_and_scanning_are_cancellable(self):
        scan_jobs.create_job("c1")
        ok, message = scan_jobs.cancel_job("c1")
        assert ok
        assert scan_jobs.get_job("c1").status == "cancelled"

        scan_jobs.create_job("c2")
        scan_jobs.update_status("c2", "scanning")
        ok, _ = scan_jobs.cancel_job("c2")
        assert ok

    def test_terminal_states_refuse(self):
        scan_jobs.create_job("c3")
        scan_jobs.update_status("c3", "done")
        ok, message = scan_jobs.cancel_job("c3")
        assert not ok
        assert "'done'" in message
        assert scan_jobs.get_job("c3").status == "done"

    def test_unknown_job_refuses(self):
        ok, message = scan_jobs.cancel_job("ghost")
        assert not ok
        assert "No such" in message


class TestRecovery:
    def test_active_scans_fail_on_startup(self):
        scan_jobs.create_job("r1")
        scan_jobs.create_job("r2")
        scan_jobs.update_status("r2", "scanning")
        scan_jobs.create_job("r3")
        scan_jobs.update_status("r3", "done")  # finished scans survive

        assert scan_jobs.recover_interrupted() == 2
        assert scan_jobs.get_job("r1").status == "failed"
        assert "restarted" in scan_jobs.get_job("r1").error
        assert scan_jobs.get_job("r2").status == "failed"
        assert scan_jobs.get_job("r3").status == "done"
