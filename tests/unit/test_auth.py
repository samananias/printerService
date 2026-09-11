"""Unit tests for the shared-PIN dependency (app/services/auth.py).

require_pin() is a plain function taking the header values, so the auth
RULES can be tested directly without HTTP: disabled when no PIN is
configured, 401 otherwise — and, since LOGIN_PLAN §3.2, also passes on a
currently-active session token in the separate X-Session-Token header.
"""

import pytest
from fastapi import HTTPException

from app.services import sessions
from app.services.auth import require_pin


class TestRequirePin:
    def test_empty_pin_disables_auth_entirely(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "")
        assert require_pin(None) is None
        assert require_pin("totally wrong") is None

    def test_correct_pin_passes(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        assert require_pin("1234") is None

    def test_wrong_pin_rejected_with_401(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        with pytest.raises(HTTPException) as exc_info:
            require_pin("9999")
        assert exc_info.value.status_code == 401

    def test_missing_header_rejected_with_401(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        with pytest.raises(HTTPException) as exc_info:
            require_pin(None)
        assert exc_info.value.status_code == 401


class TestRequirePinSessionToken:
    """The additive half of the check (LOGIN_PLAN §3.2): an active session
    token counts as a credential, without touching the PIN path above."""

    def test_active_token_passes_without_pin_header(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        token = sessions.create_session()
        assert require_pin(None, token) is None

    def test_stale_or_unknown_token_rejected(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        with pytest.raises(HTTPException) as exc_info:
            require_pin(None, "forged-token")
        assert exc_info.value.status_code == 401

    def test_empty_token_header_ignored(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        with pytest.raises(HTTPException):
            require_pin(None, "")

    def test_token_survives_after_reset_rejection(self, monkeypatch):
        """A token issued, then invalidated by a 'restart' (reset), must
        not keep working — the whole §1 answer-#4 property."""
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        token = sessions.create_session()
        sessions.reset()
        with pytest.raises(HTTPException) as exc_info:
            require_pin(None, token)
        assert exc_info.value.status_code == 401

    def test_pin_path_still_works_alongside_token_path(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "1234")
        assert require_pin("1234", None) is None
        assert require_pin("1234", "even-with-a-token-present") is None

    def test_no_pin_configured_token_irrelevant(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.API_PIN", "")
        assert require_pin(None, "anything") is None
