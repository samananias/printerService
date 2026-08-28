"""API tests for GET /printers — the detection half of the pipeline
(Section 13 test #4's logic, with the OS replaced by the fake win32print).

The 503/500 branches are tested by patching the endpoint's OWN list_printers
name — api/printers.py does `from app.printer.windows import list_printers`,
binding the function into its module namespace, so that's where the patch
must land to take effect.
"""

TEST_PRINTER = "EPSON L3210 Series"


class TestPrintersEndpoint:
    def test_lists_windows_printers(self, client, fake_win32print):
        response = client.get("/printers")

        assert response.status_code == 200
        names = [p["name"] for p in response.json()]
        assert TEST_PRINTER in names
        assert "Microsoft Print to PDF" in names

    def test_default_printer_is_flagged(self, client, fake_win32print):
        printers = {p["name"]: p["is_default"] for p in client.get("/printers").json()}
        assert printers[TEST_PRINTER] is True
        assert printers["Microsoft Print to PDF"] is False

    def test_missing_pywin32_reports_503(self, client, monkeypatch):
        def no_pywin32():
            raise ImportError("No module named 'win32print'")

        monkeypatch.setattr("app.api.printers.list_printers", no_pywin32)
        response = client.get("/printers")

        assert response.status_code == 503
        assert "pywin32" in response.json()["detail"]

    def test_other_failures_report_500(self, client, monkeypatch):
        def broken_spooler():
            raise RuntimeError("spooler unreachable")

        monkeypatch.setattr("app.api.printers.list_printers", broken_spooler)
        response = client.get("/printers")

        assert response.status_code == 500
        assert "spooler unreachable" in response.json()["detail"]
