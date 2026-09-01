"""Unit tests for the text/CSV processor (app/processors/text.py).

reportlab is a Python library, so these tests run the REAL renderer and
assert on the produced PDF bytes: the %PDF- magic, page counts (counting
/Type /Page objects), and the truncation notices (pageCompression is off
in the processor precisely so drawn text is visible in the bytes).
"""

import re

import pytest

from app.processors.base import ConversionError
from app.processors.text import (
    CSV_MAX_COLS,
    CSV_MAX_ROWS,
    MAX_TXT_PAGES,
    TextProcessor,
    decode_text,
    grid_columns,
    sniff_dialect,
    wrap_line,
)

A4_AVAIL_W = 595 - 2 * 54  # A4 minus the text margins
LINE_H = 12


def count_pages(pdf_bytes: bytes) -> int:
    """Count page objects ("Pages" is the tree node — excluded)."""
    return len(re.findall(rb"/Type /Page(?![a-zA-Z])", pdf_bytes))


class TestWrapLine:
    def test_short_line_passes_through(self):
        assert wrap_line("hello", 10) == ["hello"]

    def test_breaks_at_spaces_when_possible(self):
        assert wrap_line("hello world foo", 5) == ["hello", "world", "foo"]

    def test_long_words_are_hard_split(self):
        chunks = wrap_line("a" * 25, 10)
        assert chunks == ["a" * 10, "a" * 10, "a" * 5]

    def test_empty_line_yields_one_empty_chunk(self):
        assert wrap_line("", 10) == [""]


class TestDecodeText:
    def test_utf8(self):
        assert decode_text("héllo wörld".encode("utf-8")) == "héllo wörld"

    def test_utf16_with_bom(self):
        assert decode_text("héllo wörld".encode("utf-16")) == "héllo wörld"

    def test_windows_1252(self):
        # Smart quotes + é: invalid as UTF-8, valid as cp1252.
        raw = "café “quoted”".encode("cp1252")
        assert decode_text(raw) == "café “quoted”"

    def test_undecodable_binary_fails_instead_of_printing_mojibake(self):
        # 0x81/0x8D/0x8F/0x90/0x9D are undefined in cp1252, 0x80+ breaks
        # UTF-8 — a binary file pretending to be .txt lands here.
        with pytest.raises(ConversionError, match="does not decode"):
            decode_text(b"\x81\x8d\x8f\x90\x9d\xff\xfe\x00\x01")


class TestSniffDialect:
    def test_semicolons_detected(self):
        assert sniff_dialect("a;b;c\n1;2;3").delimiter == ";"

    def test_comma_fallback(self):
        assert sniff_dialect("plain words only").delimiter == ","


class TestGridColumns:
    def test_grid_never_exceeds_the_printable_width(self):
        rows = [["x" * 200] * 5]  # five monster cells
        widths = grid_columns(rows, A4_AVAIL_W)
        assert sum(widths) <= A4_AVAIL_W + 1e-6  # float rounding guard

    def test_narrow_content_is_not_stretched(self):
        rows = [["a", "b", "c"]]
        widths = grid_columns(rows, A4_AVAIL_W)
        assert sum(widths) < A4_AVAIL_W / 2  # left-aligned, natural size

    def test_short_cells_keep_their_content_after_padding(self):
        # The regression this pins: padding is part of the width accounting,
        # so a 2-character cell is never clipped down to "...".
        from app.processors.text import _clip_cell

        widths = grid_columns([["a1"]], A4_AVAIL_W)
        assert _clip_cell("a1", widths[0]) == "a1"


class TestProcessTxt:
    def test_renders_a_real_pdf_next_to_the_source(self, tmp_path):
        src = tmp_path / "job-1.txt"
        src.write_text("hello from a text file\n" * 10, encoding="utf-8")

        pdf = TextProcessor().process(src, tmp_path)

        assert pdf == tmp_path / "job-1.pdf"
        data = pdf.read_bytes()
        assert data.startswith(b"%PDF-")
        assert count_pages(data) == 1
        assert b"hello from a text file" in data  # compression is off on purpose
        assert src.read_bytes().startswith(b"hello")  # source untouched

    def test_long_lines_wrap_and_fill_pages(self, tmp_path):
        # 100 wrapped lines of prose — several pages' worth (61 lines/page).
        src = tmp_path / "job-2.txt"
        src.write_text(
            "\n".join("word " * 30 for _ in range(100)), encoding="utf-8"
        )

        pdf = TextProcessor().process(src, tmp_path)

        assert count_pages(pdf.read_bytes()) > 1

    def test_very_long_files_are_capped_with_a_notice(self, tmp_path):
        src = tmp_path / "job-3.txt"
        lines_per_page = int((842 - 2 * 54) // LINE_H)
        src.write_text(
            "line of text\n" * (MAX_TXT_PAGES * lines_per_page + 50),
            encoding="utf-8",
        )

        pdf = TextProcessor().process(src, tmp_path)

        data = pdf.read_bytes()
        assert count_pages(data) == MAX_TXT_PAGES
        assert b"truncated" in data

    def test_empty_file_is_an_error(self, tmp_path):
        src = tmp_path / "job-4.txt"
        src.write_bytes(b"   \n  ")
        with pytest.raises(ConversionError, match="empty"):
            TextProcessor().process(src, tmp_path)

    def test_binary_in_disguise_is_an_error(self, tmp_path):
        src = tmp_path / "job-5.txt"
        src.write_bytes(b"\x81\x8d\x8f\x90\x9d" * 4)
        with pytest.raises(ConversionError, match="does not decode"):
            TextProcessor().process(src, tmp_path)


class TestProcessCsv:
    def test_renders_a_grid_with_a_bold_header(self, tmp_path):
        src = tmp_path / "job-6.csv"
        src.write_text("name,qty,note\nbolt,12,galvanized\nnut,7,", encoding="utf-8")

        pdf = TextProcessor().process(src, tmp_path)

        data = pdf.read_bytes()
        assert data.startswith(b"%PDF-")
        assert count_pages(data) == 1
        assert b"galvanized" in data  # cell text visible in the bytes
        assert b"truncated" not in data

    def test_semicolon_files_are_detected_and_split(self, tmp_path):
        src = tmp_path / "job-7.csv"
        src.write_text("a1;a2;a3\nb1;b2;b3", encoding="utf-8")

        pdf = TextProcessor().process(src, tmp_path)

        data = pdf.read_bytes()
        assert b"a1" in data and b"b3" in data  # drawn as separate cells

    def test_row_overflow_is_capped_with_a_notice(self, tmp_path):
        src = tmp_path / "job-8.csv"
        rows = ["index,value"] + [f"{i},row {i}" for i in range(CSV_MAX_ROWS + 100)]
        src.write_text("\n".join(rows), encoding="utf-8")

        pdf = TextProcessor().process(src, tmp_path)

        data = pdf.read_bytes()
        assert count_pages(data) > 1
        assert b"truncated" in data

    def test_column_overflow_is_capped_with_a_notice(self, tmp_path):
        src = tmp_path / "job-9.csv"
        header = ",".join(f"col{i}" for i in range(CSV_MAX_COLS + 5))
        src.write_text(header, encoding="utf-8")

        pdf = TextProcessor().process(src, tmp_path)

        assert b"truncated" in pdf.read_bytes()

    def test_empty_csv_is_an_error(self, tmp_path):
        src = tmp_path / "job-10.csv"
        src.write_text(",,\n,,", encoding="utf-8")  # nothing but blank cells
        with pytest.raises(ConversionError, match="no rows"):
            TextProcessor().process(src, tmp_path)
