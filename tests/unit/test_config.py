"""Unit tests for the hand-rolled .env loader (app/config.py).

This module deliberately has no python-dotenv dependency (Constraint 6:
prefer simple technologies) — so its parsing rules are our responsibility,
and they get tests.
"""

import pytest

from app.config import _get, _load_dotenv


class TestLoadDotenv:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("KEY = value", {"KEY": "value"}),  # spaces around '='
            ("KEY=value", {"KEY": "value"}),  # no spaces at all
            ("  KEY = value  ", {"KEY": "value"}),  # outer whitespace stripped
            ("A = 1\nB = 2", {"A": "1", "B": "2"}),  # multiple lines
            ("# comment\nKEY = value", {"KEY": "value"}),  # comments skipped
            ("\n\nKEY = value\n\n", {"KEY": "value"}),  # blank lines skipped
            ("KEY", {}),  # no '=' → line ignored
            ("", {}),  # empty file
        ],
        ids=[
            "spaces-around-equals",
            "tight",
            "outer-whitespace",
            "multiple-lines",
            "comment-skipped",
            "blank-lines-skipped",
            "line-without-equals-ignored",
            "empty-file",
        ],
    )
    def test_parsing_rules(self, tmp_path, text, expected):
        env_file = tmp_path / ".env"
        env_file.write_text(text, encoding="utf-8")
        assert _load_dotenv(env_file) == expected

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert _load_dotenv(tmp_path / "does-not-exist.env") == {}


class TestGetPrecedence:
    """_get() must follow: real environment variable > .env > default."""

    KEY = "SOME_TEST_KEY"

    def test_real_environment_variable_wins(self, monkeypatch):
        monkeypatch.setenv(self.KEY, "from-environment")
        monkeypatch.setattr("app.config._ENV", {self.KEY: "from-dotenv"})
        assert _get(self.KEY, "fallback") == "from-environment"

    def test_dotenv_value_beats_default(self, monkeypatch):
        monkeypatch.delenv(self.KEY, raising=False)
        monkeypatch.setattr("app.config._ENV", {self.KEY: "from-dotenv"})
        assert _get(self.KEY, "fallback") == "from-dotenv"

    def test_default_used_when_nothing_else_set(self, monkeypatch):
        monkeypatch.delenv(self.KEY, raising=False)
        monkeypatch.setattr("app.config._ENV", {})
        assert _get(self.KEY, "fallback") == "fallback"
