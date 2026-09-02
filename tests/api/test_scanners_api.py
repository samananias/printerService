"""API tests for GET /scanners (docs/SCAN_PLAN.md §4/§9).

The endpoint's contract: it NEVER errors. Whatever the WIA layer does —
healthy, scanner-less, or on fire — the phone gets a 200 with
{"available": bool, "devices": [{"name", "id"}]}.
"""


class TestScannersEndpoint:
    def test_scanner_present_is_offered(self, client, fake_win32com):
        fake_win32com.add_device(name="EPSON L3210 Series")
        response = client.get("/scanners")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["devices"][0]["name"] == "EPSON L3210 Series"

    def test_scanner_less_setup_is_a_healthy_false(self, client, fake_win32com):
        response = client.get("/scanners")
        assert response.status_code == 200
        assert response.json() == {"available": False, "devices": []}

    def test_wia_failure_never_500s(self, client, fake_win32com):
        fake_win32com.add_device()
        fake_win32com.fail_dispatch(RuntimeError("WIA service disabled"))
        response = client.get("/scanners")
        assert response.status_code == 200
        assert response.json() == {"available": False, "devices": []}

    def test_kill_switch_hides_the_feature(
        self, client, fake_win32com, monkeypatch
    ):
        fake_win32com.add_device()
        monkeypatch.setattr("app.api.scanners.ENABLE_SCAN", False)
        response = client.get("/scanners")
        assert response.status_code == 200
        assert response.json() == {"available": False, "devices": []}

    def test_response_shape_is_exactly_the_plan(self, client, fake_win32com):
        fake_win32com.add_device()
        body = client.get("/scanners").json()
        assert set(body) == {"available", "devices"}
        assert set(body["devices"][0]) == {"name", "id"}
