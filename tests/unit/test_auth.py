"""Unit tests for the shared-PIN dependency (app/services/auth.py).

require_pin() is a plain function taking the header value, so the auth
RULES can be tested directly without HTTP: disabled when no PIN is
configured, 401 otherwise.
"""

import pytest
from fastapi import HTTPException

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
