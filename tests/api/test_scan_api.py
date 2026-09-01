"""API tests for the scan surface (docs/SCAN_PLAN.md §4/§9).

POST /scan mirrors POST /print's contract (201 + job id, work in a
background thread); refusals are 503 with an actionable message (never a
500); PIN applies to state-changing routes only.
"""

from app.services import scan_jobs


class TestPostScan:
    def test_accepts_and_queues_with_a_fake_scanner(self, client, fake_win32com):
        fake_win32com.add_device()
        response = client.post("/scan")
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"job_id", "status"}  # SCAN_PLAN §4 shape
        assert body["status"] == "queued"
        assert scan_jobs.get_job(body["job_id"]) is not None

    def test_scanner_less_setup_is_a_503_not_a_500(self, client, fake_win32com):
        response = client.post("/scan")
        assert response.status_code == 503
        assert "No scanner" in response.json()["detail"]

    def test_wia_failure_at_accept_time_is_a_503(self, client, fake_win32com):
        fake_win32com.add_device()
        fake_win32com.fail_dispatch(RuntimeError("WIA service disabled"))
        response = client.post("/scan")
        assert response.status_code == 503

    def test_kill_switch_disables_with_a_clear_message(
        self, client, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()  # hardware present, feature off
        monkeypatch.setattr("app.api.scan.ENABLE_SCAN", False)
        response = client.post("/scan")
        assert response.status_code == 503
        assert "ENABLE_SCAN=0" in response.json()["detail"]

    def test_requires_the_pin_when_one_is_configured(
        self, client, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        assert client.post("/scan").status_code == 401
        ok = client.post("/scan", headers={"X-API-PIN": "1234"})
        assert ok.status_code == 201


class TestScanStatus:
    def test_unknown_job_is_404(self, client):
        assert client.get("/scan/jobs/ghost").status_code == 404

    def test_done_scan_carries_the_download_link(
        self, client, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device()
        job_id = client.post("/scan").json()["job_id"]
        wait_for_scan_status(job_id, "done")

        body = client.get(f"/scan/jobs/{job_id}").json()
        assert body["status"] == "done"
        assert body["download_url"] == f"/scan/jobs/{job_id}/download"
        assert body["size_bytes"] > 0
        assert body["filename"].startswith("scan-")

    def test_incomplete_scan_has_no_download_link(
        self, client, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()
        monkeypatch.setattr("app.api.scan.start_scan", lambda job_id: None)
        job_id = client.post("/scan").json()["job_id"]

        body = client.get(f"/scan/jobs/{job_id}").json()
        assert body["status"] == "queued"
        assert body["download_url"] is None


class TestScanDownload:
    def test_download_before_done_is_409(self, client, fake_win32com, monkeypatch):
        fake_win32com.add_device()
        monkeypatch.setattr("app.api.scan.start_scan", lambda job_id: None)
        job_id = client.post("/scan").json()["job_id"]

        response = client.get(f"/scan/jobs/{job_id}/download")
        assert response.status_code == 409
        assert "queued" in response.json()["detail"]

    def test_download_delivers_the_finished_pdf(
        self, client, fake_win32com, wait_for_scan_status
    ):
        fake_win32com.add_device()
        job_id = client.post("/scan").json()["job_id"]
        wait_for_scan_status(job_id, "done")

        response = client.get(f"/scan/jobs/{job_id}/download")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"
        assert "attachment" in response.headers["content-disposition"]

    def test_download_unknown_job_is_404(self, client):
        assert client.get("/scan/jobs/ghost/download").status_code == 404


class TestScanCancel:
    def test_cancel_a_queued_scan(self, client, fake_win32com, monkeypatch):
        fake_win32com.add_device()
        monkeypatch.setattr("app.api.scan.start_scan", lambda job_id: None)
        job_id = client.post("/scan").json()["job_id"]

        response = client.delete(f"/scan/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        # Cancelling again refuses: the scan is already terminal.
        assert client.delete(f"/scan/jobs/{job_id}").status_code == 409

    def test_cancel_unknown_job_is_404(self, client):
        assert client.delete("/scan/jobs/ghost").status_code == 404

    def test_cancel_requires_the_pin(
        self, client, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()
        monkeypatch.setattr("app.api.scan.start_scan", lambda job_id: None)
        job_id = client.post("/scan").json()["job_id"]
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")

        assert client.delete(f"/scan/jobs/{job_id}").status_code == 401
        ok = client.delete(f"/scan/jobs/{job_id}", headers={"X-API-PIN": "1234"})
        assert ok.status_code == 200
