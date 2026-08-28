"""Unit tests for upload handling (app/services/uploads.py).

validate_pdf() is the single most security-relevant pure-logic function in
the service (SOURCE_OF_TRUTH Section 8), so it gets the boundary treatment:
what's accepted, what's rejected, and exactly WHERE the line sits.
"""

import pytest

from app.services import uploads
from app.services.uploads import (
    UploadError,
    save_upload,
    sweep_stale_uploads,
    upload_path,
    validate_pdf,
)


class TestValidatePdf:
    def test_accepts_a_real_pdf(self):
        validate_pdf("report.pdf", b"%PDF-1.4 rest of the document")  # no raise

    def test_empty_filename_skips_extension_check_but_still_checks_magic(self):
        # curl/some clients send no filename; the content check must still fire.
        validate_pdf("", b"%PDF-1.4")  # no raise

    def test_wrong_extension_rejected_with_415(self):
        with pytest.raises(UploadError) as exc_info:
            validate_pdf("notes.txt", b"%PDF-1.4")
        assert exc_info.value.status_code == 415

    @pytest.mark.parametrize("name", ["REPORT.PDF", "Report.Pdf", "x.pDf"])
    def test_extension_check_is_case_insensitive(self, name):
        validate_pdf(name, b"%PDF-1.4")  # no raise

    def test_renamed_text_file_rejected_by_magic_bytes_with_415(self):
        # A .txt renamed to .pdf passes the extension check — the %PDF- magic
        # bytes are what catch it (config.py's PDF_MAGIC).
        with pytest.raises(UploadError, match="not a PDF") as exc_info:
            validate_pdf("fake.pdf", b"just some text, definitely not a pdf")
        assert exc_info.value.status_code == 415

    def test_too_large_rejected_with_413(self, monkeypatch):
        monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 1)
        five_bytes_over = b"%PDF-" + b"x" * (1024 * 1024)
        with pytest.raises(UploadError, match="limit is 1 MB") as exc_info:
            validate_pdf("big.pdf", five_bytes_over)
        assert exc_info.value.status_code == 413

    def test_exactly_at_limit_passes(self, monkeypatch):
        # The check is strictly '>' — a file AT the limit is legitimate.
        monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 1)
        exactly_one_mb = b"%PDF-" + b"x" * (1024 * 1024 - 5)
        validate_pdf("big.pdf", exactly_one_mb)  # no raise


class TestSaveUpload:
    def test_stores_bytes_under_job_id_name(self, tmp_upload_dir):
        job_id, path = save_upload(b"%PDF-hello")
        assert path == tmp_upload_dir / f"{job_id}.pdf"
        assert path.read_bytes() == b"%PDF-hello"

    def test_job_ids_are_unique(self, tmp_upload_dir):
        first_id, _ = save_upload(b"%PDF-a")
        second_id, _ = save_upload(b"%PDF-b")
        assert first_id != second_id

    def test_creates_the_upload_dir_if_missing(self, tmp_upload_dir):
        assert not tmp_upload_dir.exists()
        save_upload(b"%PDF-x")
        assert tmp_upload_dir.exists()


class TestUploadPath:
    def test_job_id_maps_to_pdf_file_in_upload_dir(self, tmp_upload_dir):
        assert upload_path("abc123") == tmp_upload_dir / "abc123.pdf"


class TestSweepStaleUploads:
    def test_removes_only_pdfs_and_reports_count(self, tmp_upload_dir):
        tmp_upload_dir.mkdir(parents=True)
        for name in ("a.pdf", "b.pdf", "c.pdf"):
            (tmp_upload_dir / name).write_bytes(b"%PDF-x")
        (tmp_upload_dir / "keep.txt").write_bytes(b"not a pdf")

        removed = sweep_stale_uploads()

        assert removed == 3
        assert list(tmp_upload_dir.glob("*.pdf")) == []
        assert (tmp_upload_dir / "keep.txt").exists()

    def test_directory_named_like_a_pdf_never_crashes_the_sweep(self, tmp_upload_dir):
        # A directory called "weird.pdf" matches the glob but can't be
        # unlink()ed — the OSError guard must swallow it (Section 8: cleanup
        # must never crash the service).
        tmp_upload_dir.mkdir(parents=True)
        (tmp_upload_dir / "weird.pdf").mkdir()
        (tmp_upload_dir / "good.pdf").write_bytes(b"%PDF-x")

        assert sweep_stale_uploads() == 1
        assert (tmp_upload_dir / "weird.pdf").is_dir()

    def test_creates_dir_when_missing(self, tmp_upload_dir):
        assert sweep_stale_uploads() == 0
        assert tmp_upload_dir.exists()
