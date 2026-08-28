"""Unit tests for the Windows printing layer (app/printer/windows.py).

Nothing here touches a real printer. The pywin32 module is replaced by a
fake in sys.modules (the fake_win32print fixture), subprocess.run and
os.startfile are monkeypatched, and find_sumatra() searches controlled
temp directories — so the tests run on any OS.

What this pins down is the DECISION LOGIC recorded in SOURCE_OF_TRUTH
Section 5: SumatraPDF first, the Windows print-verb fallback second, and
a loud failure when no method is available.
"""

import os
import subprocess
import sys

import pytest

from app.printer import windows

TEST_PRINTER = "EPSON L3210 Series"


# ---------------------------------------------------------------------------
# find_sumatra — the search order and the "explicit path is authoritative" rule
# ---------------------------------------------------------------------------


class TestFindSumatra:
    def test_explicit_path_wins_when_it_exists(self, tmp_path, monkeypatch):
        exe = tmp_path / "SumatraPDF.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(windows, "SUMATRA_PATH", str(exe))
        assert windows.find_sumatra() == str(exe)

    def test_explicit_missing_path_is_authoritative_loudly(self, tmp_path, monkeypatch):
        # Misconfiguration must NOT silently fall back to other locations —
        # config.py's docstring promises a loud failure instead.
        monkeypatch.setattr(windows, "SUMATRA_PATH", str(tmp_path / "missing.exe"))
        monkeypatch.setattr(
            windows.shutil, "which", lambda name: "C:/elsewhere/SumatraPDF.exe"
        )
        assert windows.find_sumatra() is None

    def test_found_on_path_when_no_explicit_config(self, monkeypatch):
        monkeypatch.setattr(windows, "SUMATRA_PATH", "")
        monkeypatch.setattr(
            windows.shutil,
            "which",
            lambda name: "C:/tools/SumatraPDF.exe" if "SumatraPDF" in name else None,
        )
        assert windows.find_sumatra() == "C:/tools/SumatraPDF.exe"

    def test_found_among_standard_install_candidates(self, tmp_path, monkeypatch):
        exe = tmp_path / "SumatraPDF.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(windows, "SUMATRA_PATH", "")
        monkeypatch.setattr(windows.shutil, "which", lambda name: None)
        monkeypatch.setattr(windows, "SUMATRA_CANDIDATES", [str(exe)])
        assert windows.find_sumatra() == str(exe)

    def test_returns_none_when_nowhere_to_be_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(windows, "SUMATRA_PATH", "")
        monkeypatch.setattr(windows.shutil, "which", lambda name: None)
        monkeypatch.setattr(windows, "SUMATRA_CANDIDATES", [str(tmp_path / "nope.exe")])
        assert windows.find_sumatra() is None


# ---------------------------------------------------------------------------
# submit_pdf — the primary (SumatraPDF) path
# ---------------------------------------------------------------------------


@pytest.fixture
def recorded_run(monkeypatch):
    """Replace subprocess.run with a recorder returning success."""
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(windows.subprocess, "run", fake_run)
    return calls


class TestSubmitPdfSumatraPath:
    def test_success_builds_the_documented_command_line(
        self, fake_win32print, tmp_path, monkeypatch, recorded_run
    ):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-")
        monkeypatch.setattr(windows, "find_sumatra", lambda: "C:/SumatraPDF.exe")

        method, printer = windows.submit_pdf(pdf)

        assert (method, printer) == ("sumatrapdf", TEST_PRINTER)
        assert recorded_run["cmd"] == [
            "C:/SumatraPDF.exe",
            "-print-to",
            TEST_PRINTER,
            "-silent",
            str(pdf),
        ]

    def test_configured_printer_name_overrides_the_windows_default(
        self, fake_win32print, tmp_path, monkeypatch, recorded_run
    ):
        monkeypatch.setattr(windows, "PRINTER_NAME", "Backup Printer")
        monkeypatch.setattr(windows, "find_sumatra", lambda: "C:/SumatraPDF.exe")

        _, printer = windows.submit_pdf(tmp_path / "doc.pdf")

        assert printer == "Backup Printer"

    def test_explicit_printer_argument_wins_over_config(
        self, fake_win32print, tmp_path, monkeypatch, recorded_run
    ):
        monkeypatch.setattr(windows, "PRINTER_NAME", "Backup Printer")
        monkeypatch.setattr(windows, "find_sumatra", lambda: "C:/SumatraPDF.exe")

        _, printer = windows.submit_pdf(tmp_path / "doc.pdf", printer_name="Requested")

        assert printer == "Requested"

    def test_nonzero_sumatra_exit_raises_runtime_error_with_stderr(
        self, fake_win32print, tmp_path, monkeypatch
    ):
        def failing_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout=b"", stderr=b"printer offline\n"
            )

        monkeypatch.setattr(windows.subprocess, "run", failing_run)
        monkeypatch.setattr(windows, "find_sumatra", lambda: "C:/SumatraPDF.exe")

        with pytest.raises(RuntimeError, match="printer offline"):
            windows.submit_pdf(tmp_path / "doc.pdf")


# ---------------------------------------------------------------------------
# submit_pdf — the print-verb fallback (only when SumatraPDF is absent)
# ---------------------------------------------------------------------------


class TestSubmitPdfFallback:
    def test_print_verb_used_for_the_default_printer(
        self, fake_win32print, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(windows, "find_sumatra", lambda: None)
        started = {}
        # os.startfile exists only on Windows — raising=False lets the fake
        # be installed on Linux/CI too.
        monkeypatch.setattr(
            os, "startfile", lambda path, verb: started.update(path=path, verb=verb),
            raising=False,
        )

        method, printer = windows.submit_pdf(tmp_path / "doc.pdf")

        assert (method, printer) == ("shell-print-verb", TEST_PRINTER)
        assert started["verb"] == "print"

    def test_print_verb_refused_for_a_non_default_printer(
        self, fake_win32print, tmp_path, monkeypatch
    ):
        # The verb can only reach the Windows default printer, so asking for
        # another one must fail loudly instead of printing somewhere else.
        monkeypatch.setattr(windows, "find_sumatra", lambda: None)
        with pytest.raises(RuntimeError, match="SumatraPDF"):
            windows.submit_pdf(tmp_path / "doc.pdf", printer_name="Some Other Printer")


# ---------------------------------------------------------------------------
# win32print presence — the fail-fast contract
# ---------------------------------------------------------------------------


class TestPywin32Presence:
    def test_missing_pywin32_fails_fast(self, monkeypatch, tmp_path):
        # Setting a sys.modules entry to None makes `import win32print`
        # raise ImportError — a portable way to simulate an uninstall on
        # any OS. submit_pdf must fail immediately (before any file work).
        monkeypatch.setitem(sys.modules, "win32print", None)
        with pytest.raises(ImportError):
            windows.submit_pdf(tmp_path / "doc.pdf")

    def test_get_default_printer_reads_from_win32print(self, fake_win32print):
        assert windows.get_default_printer() == TEST_PRINTER


# ---------------------------------------------------------------------------
# list_printers — the detection half of GET /printers
# ---------------------------------------------------------------------------


class TestListPrinters:
    def test_lists_sorted_printers_with_default_flagged(self, fake_win32print):
        printers = windows.list_printers()

        assert [p.name for p in printers] == [
            TEST_PRINTER,  # sorted() puts "EPSON..." before "Microsoft..."
            "Microsoft Print to PDF",
        ]
        assert [p.is_default for p in printers] == [True, False]

    def test_default_printer_query_failure_is_tolerated(self, fake_win32print):
        def broken():
            raise RuntimeError("no default printer configured")

        fake_win32print.GetDefaultPrinter = broken

        printers = windows.list_printers()

        assert len(printers) == 2
        assert not any(p.is_default for p in printers)
