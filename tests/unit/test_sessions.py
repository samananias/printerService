"""Unit tests for the in-memory session store (app/services/sessions.py).

LOGIN_PLAN §10: create/validate, plus the "restart clears everything"
rule — simulated here with reset(), which is what a real process exit
does for free since the store is module-level memory.
"""

from app.services import sessions


class TestSessionStore:
    def test_created_token_validates(self):
        token = sessions.create_session()
        assert isinstance(token, str) and token
        assert sessions.is_valid(token) is True

    def test_unknown_token_rejected(self):
        sessions.create_session()
        assert sessions.is_valid("not-a-token") is False

    def test_none_and_empty_rejected_without_error(self):
        assert sessions.is_valid(None) is False
        assert sessions.is_valid("") is False

    def test_tokens_are_distinct_and_opaque(self):
        first = sessions.create_session()
        second = sessions.create_session()
        assert first != second
        # 256-bit urlsafe tokens: no structural prefix to guess.
        assert not first.startswith("sess")

    def test_reset_clears_every_issued_token(self):
        token = sessions.create_session()
        assert sessions.is_valid(token) is True
        sessions.reset()
        assert sessions.is_valid(token) is False
