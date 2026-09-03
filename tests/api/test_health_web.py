"""API tests for the two read-only surfaces: GET /health and GET /.

These are Section 13's test #2 ("can a client reach /health and see ok") —
minus the network hop, which stays a manual check from the phone.
"""

API_PIN = "1234"


class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_needs_no_pin_even_when_auth_is_on(self, client, monkeypatch):
        # /health is the FIRST thing to check when something's broken — it
        # must answer even if the client has no PIN (Section 8: GETs stay open).
        monkeypatch.setattr("app.services.auth.API_PIN", API_PIN)
        assert client.get("/health").status_code == 200


class TestWebPage:
    def test_root_serves_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_page_has_upload_form_and_print_button(self, client):
        page = client.get("/").text
        assert 'type="file"' in page  # the PDF picker
        assert ">Print<" in page  # the button that POSTs /print
        assert "/print" in page  # the endpoint the page's JS calls
        assert 'href="/favicon.svg"' in page

    def test_favicon_svg_served(self, client):
        response = client.get("/favicon.svg")
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert "<svg" in response.text

    def test_favicon_ico_served(self, client):
        response = client.get("/favicon.ico")
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert "<svg" in response.text


class TestScanWebUi:
    """Scan moved to its own page at GET /scan (owner request: separate page,
    always-reachable). The print page keeps one always-visible Scan nav button
    that hands off; the scan page itself degrades to a calm message when no
    scanner exists — it never errors, never breaks the print page."""

    def test_print_page_has_the_scan_handoff(self, client):
        page = client.get("/").text
        assert 'href="/scan"' in page          # the always-visible nav button
        assert '>Scan<' in page
        assert 'id="printBtn"' in page         # printing stays first

    def test_print_page_has_no_scan_ui(self, client):
        # The scan form lived on the print page before; now it's gone from it.
        page = client.get("/").text
        assert 'id="scanSection"' not in page
        assert 'id="scanBtn"' not in page

    def test_scan_page_serves_html(self, client):
        response = client.get("/scan")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_scan_page_includes_the_scan_ui_and_flow(self, client):
        page = client.get("/scan").text
        assert 'id="scanSection"' in page
        assert 'id="scanBtn"' in page             # the real button
        assert 'onclick="startScan()"' in page
        assert 'fetch("/scan")' in page or 'fetch("/scan"' in page
        assert "/scan/jobs/" in page              # poll + download link
        assert "pollScan" in page
        assert "startScan" in page
        # And a way back to printing.
        assert 'href="/"' in page

    def test_scan_page_has_nav_back_to_print(self, client):
        page = client.get("/scan").text
        assert '>Print<' in page
        assert 'aria-label="Back to the print page"' in page

    def test_scan_page_includes_the_scan_options(self, client):
        # Phase 4: DPI / color / format selects, read by startScan.
        page = client.get("/scan").text
        assert 'id="scanDpi"' in page
        assert 'id="scanColorMode"' in page
        assert 'id="scanFormat"' in page
        assert 'getElementById("scanDpi")' in page
        assert 'getElementById("scanFormat")' in page

    def test_scan_page_degrades_without_a_scanner(self, client, monkeypatch):
        # The scan page is reachable even on a scanner-less setup and shows a
        # calm line; the controls stay hidden until /scanners says otherwise.
        page = client.get("/scan").text
        assert 'id="scanStatus"' in page
        assert 'id="scanControls" style="display:none' in page
        assert "No scanner detected" in page      # wired into the JS


class TestNotebookRedesign:
    """WEBDESIGN_PLAN revision 2 (the exercise-book page): a Jobs list,
    emoji-free copy, and the self-hosted assets inlined at import."""

    def test_page_has_the_jobs_list(self, client):
        page = client.get("/").text
        assert 'id="jobList"' in page            # entries written on the rules
        assert 'id="jobsWorking"' in page        # the pencil, shown while active
        assert 'fetch("/jobs")' in page          # GET /jobs drives the list
        assert "cancelJob" in page               # DELETE for active jobs

    def test_page_uses_no_emoji(self, client):
        # Hard rule (brief §4): status is icon + exact word, never emoji.
        page = client.get("/").text
        for emoji in ["📨", "❌", "⏳", "✅", "🔁", "📇", "🖨", "📄"]:
            assert emoji not in page

    def test_assets_are_inlined_and_self_hosted(self, client):
        page = client.get("/").text
        assert "data:font/woff2;base64," in page  # Patrick Hand inlined
        assert "fonts.googleapis" not in page     # zero CDN calls at runtime
        assert '<symbol id="i-printer"' in page   # Phosphor sprite assembled
        assert '<symbol id="i-pencil"' in page    # the signature element


