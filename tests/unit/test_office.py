"""Unit tests for the office processor (app/processors/office.py).

LibreOffice is an EXTERNAL executable — the tests replace subprocess.Popen
with fakes that write the output PDF soffice would have written, so the
suite pins down everything EXCEPT LibreOffice itself:

  - the exact invocation shape (headless, private profile, convert-to pdf);
  - the failure mapping: nonzero exit / timeout / no output file / cannot
    start → ConversionError with a message a phone user can act on;
  - the kill switch: available() = ENABLE_OFFICE AND LibreOffice found.

Whether LibreOffice actually renders a DOCX correctly is T6's job on real
hardware (spike_t6_office.py) — that stays outside the automated suite,
like every paper test.
"""

import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app.processors import office
from app.processors.base import ConversionError
from app.processors.office import OfficeProcessor, find_soffice


def make_docx_bytes() -> bytes:
    """The smallest ZIP that detection/office code treats as a DOCX."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<xml/>")
    return buffer.getvalue()


class FakeProcess:
    """Stands in for subprocess.Popen's return value."""

    def __init__(self, returncode=0, stderr=b"", raises_timeout=False):
        self.pid = 4242
        self.returncode = returncode
        self._stderr = stderr
        self._raises_timeout = raises_timeout
        self.kill_calls = 0
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        # Only the FIRST wait can time out — after the kill, the reap must
        # return normally (that's the real subprocess contract the code
        # relies on).
        if self._raises_timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="soffice", timeout=timeout)
        return b"", self._stderr

    def kill(self):
        self.kill_calls += 1


# ---------------------------------------------------------------------------
# find_soffice — search order and the "explicit path is authoritative" rule
# ---------------------------------------------------------------------------


class TestFindSoffice:
    def test_explicit_path_wins_when_it_exists(self, tmp_path, monkeypatch):
        exe = tmp_path / "soffice.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(office, "LO_PATH", str(exe))
        assert find_soffice() == str(exe)

    def test_explicit_missing_path_is_authoritative_loudly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(office, "LO_PATH", str(tmp_path / "missing.exe"))
        monkeypatch.setattr(
            office.shutil, "which", lambda name: "C:/elsewhere/soffice.exe"
        )
        assert find_soffice() is None

    def test_found_on_path_when_no_explicit_config(self, monkeypatch):
        monkeypatch.setattr(office, "LO_PATH", "")
        monkeypatch.setattr(
            office.shutil,
            "which",
            lambda name: "C:/LibreOffice/soffice.exe" if "soffice" in name else None,
        )
        assert find_soffice() == "C:/LibreOffice/soffice.exe"

    def test_found_among_standard_install_candidates(self, tmp_path, monkeypatch):
        exe = tmp_path / "soffice.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(office, "LO_PATH", "")
        monkeypatch.setattr(office.shutil, "which", lambda name: None)
        monkeypatch.setattr(office, "SOFFICE_CANDIDATES", [str(exe)])
        assert find_soffice() == str(exe)

    def test_returns_none_when_nowhere_to_be_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(office, "LO_PATH", "")
        monkeypatch.setattr(office.shutil, "which", lambda name: None)
        monkeypatch.setattr(office, "SOFFICE_CANDIDATES", [str(tmp_path / "nope.exe")])
        assert find_soffice() is None


# ---------------------------------------------------------------------------
# available() — the office kill switch
# ---------------------------------------------------------------------------


class TestAvailable:
    def test_disabled_by_config_even_when_installed(self, monkeypatch):
        monkeypatch.setattr(office, "ENABLE_OFFICE", False)
        monkeypatch.setattr(office, "find_soffice", lambda: "C:/soffice.exe")
        assert OfficeProcessor().available() is False

    def test_unavailable_when_libreoffice_missing(self, monkeypatch):
        monkeypatch.setattr(office, "ENABLE_OFFICE", True)
        monkeypatch.setattr(office, "find_soffice", lambda: None)
        assert OfficeProcessor().available() is False

    def test_available_when_enabled_and_installed(self, monkeypatch):
        monkeypatch.setattr(office, "ENABLE_OFFICE", True)
        monkeypatch.setattr(office, "find_soffice", lambda: "C:/soffice.exe")
        assert OfficeProcessor().available() is True


# ---------------------------------------------------------------------------
# process() — the subprocess contract, with LibreOffice faked
# ---------------------------------------------------------------------------


@pytest.fixture
def soffice_found(monkeypatch):
    monkeypatch.setattr(office, "find_soffice", lambda: "C:/LibreOffice/soffice.exe")


class TestProcess:
    def test_converts_with_the_documented_headless_invocation(
        self, tmp_path, monkeypatch, soffice_found
    ):
        src = tmp_path / "job-1.docx"
        src.write_bytes(make_docx_bytes())
        calls = {}

        def fake_popen(cmd, **kwargs):
            calls["cmd"] = cmd
            outdir = Path(cmd[cmd.index("--outdir") + 1])
            (outdir / "job-1.pdf").write_bytes(b"%PDF- converted")
            return FakeProcess()

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)

        pdf = OfficeProcessor().process(src, tmp_path)

        assert pdf == tmp_path / "job-1.pdf"  # <job_id>.pdf, per the pipeline
        cmd = calls["cmd"]
        assert cmd[0] == "C:/LibreOffice/soffice.exe"
        assert "--headless" in cmd and "--norestore" in cmd and "--nolockcheck" in cmd
        assert cmd[cmd.index("--convert-to") + 1] == "pdf"
        assert cmd[cmd.index("--outdir") + 1] == str(tmp_path)
        assert cmd[-1] == str(src)
        # A fresh throwaway profile per run, passed as a file URI.
        profile_flag = next(flag for flag in cmd if flag.startswith("-env:UserInstallation="))
        assert profile_flag.startswith("-env:UserInstallation=file:///")

    def test_each_conversion_gets_a_fresh_profile(
        self, tmp_path, monkeypatch, soffice_found
    ):
        src = tmp_path / "job-2.docx"
        src.write_bytes(make_docx_bytes())
        profiles = []

        def fake_popen(cmd, **kwargs):
            profiles.append(
                next(f for f in cmd if f.startswith("-env:UserInstallation="))
            )
            outdir = Path(cmd[cmd.index("--outdir") + 1])
            src = Path(cmd[-1])
            (outdir / f"{src.stem}.pdf").write_bytes(b"%PDF-")
            return FakeProcess()

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)
        for number in range(2):
            (tmp_path / f"job-2-{number}.docx").write_bytes(make_docx_bytes())
            OfficeProcessor().process(tmp_path / f"job-2-{number}.docx", tmp_path)

        assert profiles[0] != profiles[1]  # a crashed run can't poison the next

    def test_nonzero_exit_becomes_a_conversion_error_with_stderr(
        self, tmp_path, monkeypatch, soffice_found
    ):
        (tmp_path / "job-3.docx").write_bytes(make_docx_bytes())

        def fake_popen(cmd, **kwargs):
            return FakeProcess(returncode=3, stderr=b"Error: source could not be loaded\n")

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)

        with pytest.raises(ConversionError, match="exit 3.*could not be loaded"):
            OfficeProcessor().process(tmp_path / "job-3.docx", tmp_path)

    def test_timeout_kills_the_process_tree_and_explains_itself(
        self, tmp_path, monkeypatch, soffice_found
    ):
        (tmp_path / "job-4.docx").write_bytes(make_docx_bytes())
        processes = []

        def fake_popen(cmd, **kwargs):
            process = FakeProcess(raises_timeout=True)
            processes.append(process)
            return process

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)
        # Task Manager for robots: record whatever kill mechanism runs.
        kills = []
        monkeypatch.setattr(
            office.subprocess, "run", lambda cmd, **kw: kills.append(cmd)
        )

        with pytest.raises(ConversionError, match="did not finish within"):
            OfficeProcessor().process(tmp_path / "job-4.docx", tmp_path)

        process = processes[0]
        # Reaped after the kill attempt, on every platform (taskkill on
        # Windows, kill() elsewhere).
        assert process.communicate_calls == 2
        if process.kill_calls:
            assert kills == []  # kill() path means no taskkill was needed
        else:
            assert kills and kills[0][0] == "taskkill"

    def test_missing_output_pdf_is_an_error_even_at_exit_zero(
        self, tmp_path, monkeypatch, soffice_found
    ):
        (tmp_path / "job-5.docx").write_bytes(make_docx_bytes())

        def fake_popen(cmd, **kwargs):
            return FakeProcess()  # exit 0, but writes nothing

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)

        with pytest.raises(ConversionError, match="produced no PDF"):
            OfficeProcessor().process(tmp_path / "job-5.docx", tmp_path)

    def test_failure_to_start_libreoffice_is_a_conversion_error(
        self, tmp_path, monkeypatch, soffice_found
    ):
        (tmp_path / "job-6.docx").write_bytes(make_docx_bytes())

        def fake_popen(cmd, **kwargs):
            raise OSError("soffice vanished")

        monkeypatch.setattr(office.subprocess, "Popen", fake_popen)

        with pytest.raises(ConversionError, match="Could not start LibreOffice"):
            OfficeProcessor().process(tmp_path / "job-6.docx", tmp_path)

    def test_missing_libreoffice_fails_with_an_actionable_message(
        self, tmp_path, monkeypatch
    ):
        # The pipeline-side safety net for a machine that changed after the
        # upload was accepted (config flip, uninstall).
        monkeypatch.setattr(office, "find_soffice", lambda: None)

        (tmp_path / "job-7.docx").write_bytes(make_docx_bytes())
        with pytest.raises(ConversionError, match="Convert it to PDF first"):
            OfficeProcessor().process(tmp_path / "job-7.docx", tmp_path)
