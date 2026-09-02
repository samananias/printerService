"""Unit tests for upload handling (app/services/uploads.py).

validate_upload() is the single most security-relevant pure-logic function
in the service (SOURCE_OF_TRUTH Section 8), so it gets the boundary
treatment: what's accepted, what's rejected, and exactly WHERE the line
sits. Phase 1 registers only the PDF processor, so the image/office/text
cases here prove files are DETECTED correctly and then refused until their
phase lands (docs/MULTI_FORMAT_PLAN.md §10).
"""

import zipfile
from io import BytesIO

import pytest

from app.services import uploads
from app.services.uploads import (
    UploadError,
    delete_job_files,
    save_upload,
    sweep_stale_uploads,
    upload_path,
    validate_upload,
)


def make_docx_bytes() -> bytes:
    """The smallest ZIP that detection treats as a DOCX (word/ part)."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<xml/>")
    return buffer.getvalue()


class TestValidateUpload:
    def test_accepts_a_real_pdf(self):
        assert validate_upload("report.pdf", b"%PDF-1.4 rest of the document") == "pdf"

    def test_empty_filename_skips_extension_check_but_still_checks_magic(self):
        # curl/some clients send no filename; the content check must still fire.
        assert validate_upload("", b"%PDF-1.4") == "pdf"

    @pytest.mark.parametrize("name", ["REPORT.PDF", "Report.Pdf", "x.pDf"])
    def test_extension_check_is_case_insensitive(self, name):
        assert validate_upload(name, b"%PDF-1.4") == "pdf"

    def test_unsupported_extension_rejected_with_415(self):
        with pytest.raises(UploadError) as exc_info:
            validate_upload("virus.exe", b"MZ\x90\x00")
        assert exc_info.value.status_code == 415
        assert "pdf" in str(exc_info.value).lower()  # the message names what IS allowed

    def test_recognizable_content_with_a_lying_extension_is_still_refused(self):
        # Even PDF bytes don't smuggle a file in under an unknown extension:
        # the allowlist stays explicit (plan Section 9) — the client must
        # name the file correctly too.
        with pytest.raises(UploadError, match="Unsupported file type"):
            validate_upload("report.exe", b"%PDF-1.4 real pdf")

    def test_renamed_text_file_rejected_by_magic_bytes_with_415(self):
        # A .txt renamed to .pdf passes the extension check — the %PDF- magic
        # bytes are what catch it (detection.py, fed by config.PDF_MAGIC).
        with pytest.raises(UploadError, match="not a PDF") as exc_info:
            validate_upload("fake.pdf", b"just some text, definitely not a pdf")
        assert exc_info.value.status_code == 415

    def test_empty_pdf_rejected_by_magic_bytes(self):
        # An empty file carries no signature — same fate as a renamed one.
        with pytest.raises(UploadError, match="not a PDF"):
            validate_upload("empty.pdf", b"")

    def test_text_extension_with_binary_content_is_a_mismatch(self):
        # The extension says "text", the bytes say "PDF" — extensions lie,
        # and detection must say so instead of guessing.
        with pytest.raises(UploadError, match="does not match"):
            validate_upload("notes.txt", b"%PDF-1.4")

    def test_images_are_now_printable(self):
        # Phase 2 registered the image processor: a real JPEG is accepted
        # and its category flows to the job/pipeline.
        assert validate_upload("photo.jpg", b"\xff\xd8\xff\xe0" + b"x" * 32) == "image"

    def test_office_file_accepted_when_libreoffice_is_available(self, monkeypatch):
        # Phase 3 registered the office processor; acceptance depends on
        # the machine having LibreOffice (patched here — the dev/CI boxes
        # don't have it, which is exactly the state the next test pins).
        monkeypatch.setattr(
            "app.processors.office.OfficeProcessor.available", lambda self: True
        )
        assert validate_upload("invoice.docx", make_docx_bytes()) == "office"

    def test_office_file_refused_with_an_actionable_message_when_unavailable(
        self, monkeypatch
    ):
        # The kill switch / missing LibreOffice: registered, but not
        # runnable — the message must say what to DO, not just "no".
        monkeypatch.setattr(
            "app.processors.office.OfficeProcessor.available", lambda self: False
        )
        with pytest.raises(UploadError, match="LibreOffice") as exc_info:
            validate_upload("invoice.docx", make_docx_bytes())
        assert exc_info.value.status_code == 415

    def test_text_files_are_now_printable(self):
        # Phase 4 registered the text processor; text has no magic bytes,
        # so the extension is the trusted signal here (detection.py).
        assert validate_upload("notes.txt", b"just some plain text content") == "text"
        assert validate_upload("data.csv", b"a,b,c\n1,2,3") == "text"

    def test_unregistered_category_refused_until_its_phase(self, monkeypatch):
        # All current categories are registered, so the "later phase" gate
        # has no natural case left — simulate a future category whose
        # processor isn't registered yet to keep the branch honest.
        monkeypatch.setattr(
            "app.services.uploads.for_category", lambda category: None
        )
        with pytest.raises(UploadError, match="later phase") as exc_info:
            validate_upload("notes.txt", b"just some plain text content")
        assert exc_info.value.status_code == 415

    def test_no_filename_and_unknown_content_is_unsupported(self):
        # No extension to hint from AND no magic to prove anything with —
        # the honest answer is "unsupported", not a guess.
        with pytest.raises(UploadError, match="no extension"):
            validate_upload("", b"random junk")

    def test_macro_office_formats_rejected_by_policy(self):
        # Macro-enabled formats are refused before anything else looks at
        # the content (plan Section 9) — policy, not a content check.
        with pytest.raises(UploadError, match="[Mm]acro") as exc_info:
            validate_upload("invoice.docm", b"PK\x03\x04 whatever")
        assert exc_info.value.status_code == 415

    def test_too_large_rejected_with_413(self, monkeypatch):
        monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 1)
        five_bytes_over = b"%PDF-" + b"x" * (1024 * 1024)
        with pytest.raises(UploadError, match="limit is 1 MB") as exc_info:
            validate_upload("big.pdf", five_bytes_over)
        assert exc_info.value.status_code == 413

    def test_exactly_at_limit_passes(self, monkeypatch):
        # The check is strictly '>' — a file AT the limit is legitimate.
        monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 1)
        exactly_one_mb = b"%PDF-" + b"x" * (1024 * 1024 - 5)
        assert validate_upload("big.pdf", exactly_one_mb) == "pdf"


class TestSaveUpload:
    def test_stores_bytes_under_job_id_name(self, tmp_upload_dir):
        job_id, path = save_upload(b"%PDF-hello")
        assert path == tmp_upload_dir / f"{job_id}.pdf"
        assert path.read_bytes() == b"%PDF-hello"

    def test_extension_is_stored_with_the_file(self, tmp_upload_dir):
        # Non-PDF phases will store the real extension; the mechanism
        # already works (and keeps a client's ".JPG" lowercase).
        job_id, path = save_upload(b"\xff\xd8\xffjpg-bytes", ext=".jpg")
        assert path == tmp_upload_dir / f"{job_id}.jpg"

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

    def test_extension_parameter_maps_the_same_way(self, tmp_upload_dir):
        assert upload_path("abc123", ".jpg") == tmp_upload_dir / "abc123.jpg"


class TestDeleteJobFiles:
    def test_deletes_every_file_of_a_job_and_reports_count(self, tmp_upload_dir):
        # A job can own several files (source upload + converted PDF once
        # non-PDF formats land) — cleanup must take them all, only them.
        tmp_upload_dir.mkdir(parents=True)
        (tmp_upload_dir / "job-1.pdf").write_bytes(b"x")
        (tmp_upload_dir / "job-1.jpg").write_bytes(b"x")
        (tmp_upload_dir / "other.pdf").write_bytes(b"x")

        assert delete_job_files("job-1") == 2
        assert (tmp_upload_dir / "other.pdf").exists()

    def test_missing_job_is_a_clean_no_op(self, tmp_upload_dir):
        tmp_upload_dir.mkdir(parents=True)
        assert delete_job_files("ghost") == 0


class TestSweepStaleUploads:
    def test_removes_every_stale_file_and_reports_count(self, tmp_upload_dir):
        # uploads/ is service-managed (every name in it is server-generated),
        # so ANY file left by a previous run is stale — including files of
        # formats that didn't exist when the sweep was PDF-only.
        tmp_upload_dir.mkdir(parents=True)
        for name in ("a.pdf", "b.pdf", "c.jpg"):
            (tmp_upload_dir / name).write_bytes(b"%PDF-x")

        removed = sweep_stale_uploads()

        assert removed == 3
        assert list(tmp_upload_dir.iterdir()) == []

    def test_directory_named_like_a_pdf_never_crashes_the_sweep(self, tmp_upload_dir):
        # A directory called "weird.pdf" must be skipped (is_file check),
        # not crash the sweep (Section 8: cleanup must never crash the
        # service) and not be deleted either.
        tmp_upload_dir.mkdir(parents=True)
        (tmp_upload_dir / "weird.pdf").mkdir()
        (tmp_upload_dir / "good.pdf").write_bytes(b"%PDF-x")

        assert sweep_stale_uploads() == 1
        assert (tmp_upload_dir / "weird.pdf").is_dir()

    def test_creates_dir_when_missing(self, tmp_upload_dir):
        assert sweep_stale_uploads() == 0
        assert tmp_upload_dir.exists()

    def test_dotfiles_like_gitkeep_survive_the_sweep(self, tmp_upload_dir):
        # .gitkeep exists only so git tracks the (normally empty) uploads/
        # directory in the repo. It is not a job leftover and must survive
        # every sweep — regression: the startup sweep used to delete it,
        # silently dropping uploads/ from the repository.
        tmp_upload_dir.mkdir(parents=True)
        (tmp_upload_dir / ".gitkeep").write_bytes(b"")
        (tmp_upload_dir / "stale.pdf").write_bytes(b"%PDF-x")

        assert sweep_stale_uploads() == 1
        assert (tmp_upload_dir / ".gitkeep").is_file()
        assert not (tmp_upload_dir / "stale.pdf").exists()
