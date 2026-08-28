"""Unit tests for format detection (app/detection.py).

Detection is pure logic — no HTTP, no disk, no status codes — so these
tests pin its rules:
  - extension is only a hint (category_for);
  - magic bytes are the evidence (magic_category);
  - ZIP/OLE containers are sniffed to confirm they really are office docs;
  - text has no signature, so it is classified by extension only.
"""

import io
import zipfile

import pytest

from app.detection import category_for, magic_category

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
WEBP = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 4
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8
ZIP_PLAIN = b"PK\x03\x04" + b"\x00" * 8  # a zip that is not an office document
RUBBISH = b"definitely not any known format"


def build_ooxml(part_prefix: str) -> bytes:
    """A real (small) zip whose entry names look like an OOXML document."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{part_prefix}/document.xml", b"<xml/>")
    return buffer.getvalue()


class TestMagicCategory:
    def test_pdf_magic(self):
        assert magic_category(b"%PDF-1.7 trailing bytes") == "pdf"

    def test_jpeg_magic(self):
        assert magic_category(JPEG) == "image"

    def test_png_magic(self):
        assert magic_category(PNG) == "image"

    def test_webp_magic_needs_the_riff_subtype(self):
        assert magic_category(WEBP) == "image"
        # "RIFF" alone (e.g. a WAV file) is not an image — offset 8 must say WEBP.
        assert magic_category(b"RIFF\x24\x00\x00\x00WAVE") is None
        assert magic_category(b"RIFF") is None  # truncated: no decision either way

    def test_ole_magic_is_office(self):
        assert magic_category(OLE) == "office"

    def test_ooxml_containers_are_office(self):
        for prefix in ("word", "xl", "ppt"):
            assert magic_category(build_ooxml(prefix)) == "office"

    def test_odf_mimetype_entry_is_office(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        assert magic_category(buffer.getvalue()) == "office"

    def test_plain_zip_is_not_office(self):
        assert magic_category(ZIP_PLAIN) is None

    def test_corrupt_zip_is_not_office(self):
        assert magic_category(b"PK\x03\x04this is not really a zip") is None

    def test_rubbish_is_unknown(self):
        assert magic_category(RUBBISH) is None

    def test_empty_bytes_are_unknown(self):
        assert magic_category(b"") is None


class TestCategoryFor:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("report.pdf", "pdf"),
            ("REPORT.PDF", "pdf"),
            ("photo.jpg", "image"),
            ("photo.JPEG", "image"),
            ("shot.webp", "image"),
            ("invoice.docx", "office"),
            ("sheet.xls", "office"),
            ("deck.pptx", "office"),
            ("notes.txt", "text"),
            ("data.csv", "text"),
        ],
    )
    def test_known_extensions(self, filename, expected):
        assert category_for(filename) == expected

    @pytest.mark.parametrize("filename", ["virus.exe", "archive.zip", "", "noext"])
    def test_unknown_or_absent_extensions_return_none(self, filename):
        assert category_for(filename) is None
