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

