"""Unit tests for app/services/downloads.py (docs/SCAN_PLAN.md §5/§7).

downloads/ is uploads/' twin: server-generated names, dotfiles survive
the sweep, everything else is startup-swept.
"""

from app.services import downloads


class TestPaths:
    def test_result_and_working_paths_are_server_generated(self):
        assert downloads.result_path("j1").name == "j1.pdf"
        assert downloads.working_path("j1").name == "j1.png"


class TestJobFiles:
    def test_job_files_and_delete(self, tmp_download_dir):
        downloads.working_path("j1").write_bytes(b"png")
        downloads.result_path("j1").write_bytes(b"pdf")
        assert len(downloads.job_files("j1")) == 2
        assert downloads.delete_job_files("j1") == 2
        assert downloads.job_files("j1") == []

    def test_delete_ignores_foreign_files(self, tmp_download_dir):
        (tmp_download_dir / "other.pdf").write_bytes(b"x")
        assert downloads.delete_job_files("j1") == 0
        assert (tmp_download_dir / "other.pdf").exists()


class TestSweep:
    def test_sweep_removes_files_but_keeps_dotfiles(self, tmp_download_dir):
        (tmp_download_dir / "abc.pdf").write_bytes(b"x")
        (tmp_download_dir / "def.png").write_bytes(b"y")
        (tmp_download_dir / ".gitkeep").write_text("")

        removed = downloads.sweep_stale_downloads()

        assert removed == 2
        assert (tmp_download_dir / ".gitkeep").exists()
        assert not (tmp_download_dir / "abc.pdf").exists()

    def test_sweep_on_a_missing_directory_creates_it(self, tmp_download_dir, monkeypatch):
        import shutil

        shutil.rmtree(tmp_download_dir)
        assert downloads.sweep_stale_downloads() == 0
        assert tmp_download_dir.is_dir()
