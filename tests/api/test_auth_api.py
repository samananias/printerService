"""API tests for the PIN login gate endpoints (docs/LOGIN_PLAN.md §4/§10).

/auth/status must never error and must report the full
pin_required/session_valid (true/false/null) matrix; /auth/login must
issue a usable token on the right PIN and refuse everything else. A final
integration test proves the issued token actually unlocks a state-changing
route via X-Session-Token, and that the old X-API-PIN path is untouched.
"""

import pytest

from app.services import sessions


@pytest.fixture
def pin_on(monkeypatch):
    """A configured PIN, patched where it is actually READ (imported by
    value into both consumers — conftest.py rule #2)."""
    monkeypatch.setattr("app.services.auth.API_PIN", "1234")
    monkeypatch.setattr("app.api.auth.API_PIN", "1234")


class TestAuthStatus:
    def test_no_pin_configured_gate_does_not_exist(self, client):
        response = client.get("/auth/status")
        assert response.status_code == 200
        assert response.json() == {"pin_required": False, "session_valid": None}

    def test_pin_configured_no_token_sent(self, client, pin_on):
        response = client.get("/auth/status")
        assert response.status_code == 200
        assert response.json() == {"pin_required": True, "session_valid": None}

    def test_stale_token_reported_false_not_error(self, client, pin_on):
        response = client.get(
            "/auth/status", headers={"X-Session-Token": "expired-or-forged"}
        )
        assert response.status_code == 200
        assert response.json() == {"pin_required": True, "session_valid": False}

    def test_valid_token_reported_true(self, client, pin_on):
        token = sessions.create_session()
        response = client.get(
            "/auth/status", headers={"X-Session-Token": token}
        )
        assert response.status_code == 200
        assert response.json() == {"pin_required": True, "session_valid": True}


class TestAuthLogin:
    def test_correct_pin_returns_usable_token(self, client, pin_on):
        response = client.post("/auth/login", json={"pin": "1234"})
        assert response.status_code == 200
        token = response.json()["token"]
        assert token and sessions.is_valid(token)

    def test_wrong_pin_rejected_with_401(self, client, pin_on):
        response = client.post("/auth/login", json={"pin": "9999"})
        assert response.status_code == 401
        assert "PIN" in response.json()["detail"]

    def test_missing_field_is_422(self, client, pin_on):
        response = client.post("/auth/login", json={})
        assert response.status_code == 422

    def test_no_pin_configured_is_400(self, client):
        response = client.post("/auth/login", json={"pin": "1234"})
        assert response.status_code == 400
        assert "No PIN" in response.json()["detail"]

    def test_empty_pin_rejected(self, client, pin_on):
        response = client.post("/auth/login", json={"pin": ""})
        assert response.status_code == 401


class TestTokenUnlocksStateChangingRoutes:
    """The end-to-end point of the feature: one login, then the token
    stands in for the PIN everywhere require_pin is attached — while the
    raw-PIN path keeps working exactly as before (regression guard)."""

    def test_login_then_token_works_on_protected_route(self, client, pin_on):
        token = client.post("/auth/login", json={"pin": "1234"}).json()["token"]

        cancelled = client.delete(
            "/jobs/does-not-matter", headers={"X-Session-Token": token}
        )
        # 404 (unknown job) NOT 401 — the token got through the gate.
        assert cancelled.status_code == 404

    def test_stale_token_still_401_on_protected_route(self, client, pin_on):
        response = client.delete(
            "/jobs/does-not-matter", headers={"X-Session-Token": "forged"}
        )
        assert response.status_code == 401

    def test_raw_pin_header_path_untouched(self, client, pin_on):
        wrong = client.delete("/jobs/abc", headers={"X-API-PIN": "0000"})
        right = client.delete("/jobs/abc", headers={"X-API-PIN": "1234"})
        assert wrong.status_code == 401
        assert right.status_code == 404  # past auth, unknown job
