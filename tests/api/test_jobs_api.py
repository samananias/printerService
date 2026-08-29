"""API tests for the job-tracking endpoints (GET /jobs, GET /jobs/{id},
DELETE /jobs/{id}) — Section 11's visibility + cancel surface.

These tests create jobs directly through the store (the same functions the
upload endpoint calls) instead of round-tripping through POST /print —
unit-style setup, API-style assertions.
"""

from app.models.printing import JobStatus
from app.services import jobs


def seed_job(tmp_upload_dir, job_id="abc123", pdf=True):
    """Create a job directly, optionally with its upload file on disk."""
    pdf_path = tmp_upload_dir / f"{job_id}.pdf"
    if pdf:
        pdf_path.write_bytes(b"%PDF-1.4 x")
    return jobs.create_job(job_id, "file.pdf", 9, pdf_path)


class TestListJobs:
    def test_empty_store_returns_empty_list(self, client):
        assert client.get("/jobs").json() == []

    def test_lists_created_jobs(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "job-a")
        seed_job(tmp_upload_dir, "job-b")

        listed = client.get("/jobs").json()

        assert [j["job_id"] for j in listed] == ["job-a", "job-b"]
        assert all(j["status"] == JobStatus.RECEIVED for j in listed)


class TestOneJob:
    def test_returns_the_job(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "abc123")

        body = client.get("/jobs/abc123").json()

        assert body["job_id"] == "abc123"
        assert body["filename"] == "file.pdf"
        assert body["size_bytes"] == 9

    def test_unknown_id_returns_404(self, client):
        response = client.get("/jobs/ghost")
        assert response.status_code == 404


class TestCancelJob:
    def test_cancels_a_received_job_and_removes_its_file(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "abc123")

        response = client.delete("/jobs/abc123")

        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.CANCELLED
        assert not (tmp_upload_dir / "abc123.pdf").exists()

    def test_cancelling_a_printed_job_conflicts_409(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "abc123")
        jobs.update_status("abc123", JobStatus.DONE, printer="EPSON L3210 Series")

        response = client.delete("/jobs/abc123")

        assert response.status_code == 409
        assert response.json()["detail"]  # human-readable reason included

    def test_cancelling_unknown_job_404(self, client):
        assert client.delete("/jobs/ghost").status_code == 404

    def test_cancelling_while_printing_purges_the_spooler(
        self, client, tmp_upload_dir, fake_win32print
    ):
        # p14: a printing-stage cancel is best-effort — our queued spooler
        # jobs are purged, the job is marked cancelled either way.
        seed_job(tmp_upload_dir, "abc123")
        jobs.update_status("abc123", JobStatus.PRINTING)
        fake_win32print._spooler_jobs = [{"JobId": 42, "pDocument": "abc123.pdf"}]

        response = client.delete("/jobs/abc123")

        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.CANCELLED
        assert fake_win32print.setjob_calls == [
            ("handle:EPSON L3210 Series", 42, fake_win32print.JOB_CONTROL_DELETE)
        ]

    def test_pin_enforced_on_cancel_when_configured(self, client, tmp_upload_dir, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        seed_job(tmp_upload_dir, "abc123")

        no_header = client.delete("/jobs/abc123")
        wrong_pin = client.delete("/jobs/abc123", headers={"X-API-PIN": "0000"})
        correct = client.delete("/jobs/abc123", headers={"X-API-PIN": "1234"})

        assert no_header.status_code == 401
        assert wrong_pin.status_code == 401
        assert correct.status_code == 200


class TestRetryJob:
    def test_requeues_a_failed_job_from_its_stored_upload(
        self, client, tmp_upload_dir, mock_print, wait_for_status
    ):
        seed_job(tmp_upload_dir, "abc123")
        jobs.update_status("abc123", JobStatus.FAILED, error="printer offline")

        response = client.post("/jobs/abc123/retry")

        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.QUEUED

        job = wait_for_status("abc123", JobStatus.DONE)
        assert job.error is None  # the retry started clean and succeeded

    def test_retry_unknown_job_404(self, client):
        assert client.post("/jobs/ghost/retry").status_code == 404

    def test_retry_refused_for_non_failed_jobs(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "abc123")  # still just 'received'

        response = client.post("/jobs/abc123/retry")

        assert response.status_code == 409
        assert "only failed jobs" in response.json()["detail"]

    def test_retry_refused_when_the_upload_is_gone(self, client, tmp_upload_dir):
        seed_job(tmp_upload_dir, "abc123", pdf=False)  # no file on disk
        jobs.update_status("abc123", JobStatus.FAILED, error="printer offline")

        response = client.post("/jobs/abc123/retry")

        assert response.status_code == 409
        assert "gone" in response.json()["detail"]

    def test_pin_enforced_on_retry_when_configured(
        self, client, tmp_upload_dir, monkeypatch, mock_print
    ):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        seed_job(tmp_upload_dir, "abc123")
        jobs.update_status("abc123", JobStatus.FAILED, error="x")

        no_header = client.post("/jobs/abc123/retry")
        wrong_pin = client.post("/jobs/abc123/retry", headers={"X-API-PIN": "0000"})
        correct = client.post("/jobs/abc123/retry", headers={"X-API-PIN": "1234"})

        assert no_header.status_code == 401
        assert wrong_pin.status_code == 401
        assert correct.status_code == 200
