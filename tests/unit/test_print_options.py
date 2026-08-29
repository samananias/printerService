"""Unit tests for print options (Phase 7): validation and the SumatraPDF
print-settings builder.

The design rules pinned here:
  - defaults mean NO -print-settings at all (byte-identical to the
    T4-proven command);
  - the request's paper beats the PAPER_SIZE config; "fit" only rides
    along with a paper size;
  - `pages` is a strict allowlist (it goes into a command line);
  - the paper keys are shared between validation, page layout and the
    print engine — they must never drift apart.
"""

import pytest

from app.models.printing import (
    PAPER_CHOICES,
    PrintOptions,
    validate_print_options,
)
from app.printer import windows
from app.printer.windows import build_print_settings
from app.processors import base as processor_base


class TestValidatePrintOptions:
    def test_defaults_normalize_to_the_default_model(self):
        assert validate_print_options(1, "", "", "color") == PrintOptions()

    def test_input_is_normalized(self):
        options = validate_print_options(3, " 1-3,5 ", " A4 ", " Monochrome ")
        assert options.copies == 3
        assert options.pages == "1-3,5"
        assert options.paper == "a4"
        assert options.color_mode == "monochrome"

    @pytest.mark.parametrize("copies", [0, -1, 100])
    def test_copies_bounds(self, copies):
        with pytest.raises(ValueError, match="between 1 and 99"):
            validate_print_options(copies, "", "", "color")

    @pytest.mark.parametrize("pages", ["1;2", "drop tables", "1--2", "abc", "1-3,"])
    def test_pages_is_an_allowlist(self, pages):
        with pytest.raises(ValueError, match="Pages must look like"):
            validate_print_options(1, pages, "", "color")

    @pytest.mark.parametrize("pages", ["5", "2-6", "1-3,5,8-10", "odd", "even", "10-8"])
    def test_pages_accepts_documented_shapes(self, pages):
        # 10-8 is a REVERSED range — SumatraPDF prints it back-to-front,
        # so it's allowed on purpose.
        assert validate_print_options(1, pages, "", "color").pages == pages

    def test_pages_length_cap(self):
        with pytest.raises(ValueError, match="too long"):
            validate_print_options(1, "1," * 60, "", "color")

    def test_paper_allowlist(self):
        with pytest.raises(ValueError, match="Paper must be one of"):
            validate_print_options(1, "", "glossy", "color")

    def test_color_mode_allowlist(self):
        with pytest.raises(ValueError, match="Color mode"):
            validate_print_options(1, "", "", "sepia")


class TestBuildPrintSettings:
    def test_defaults_mean_no_settings_at_all(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert build_print_settings(None) is None
        assert build_print_settings(PrintOptions()) is None

    def test_paper_token_gains_fit(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert build_print_settings(PrintOptions(paper="a4")) == "paper=A4,fit"

    def test_long_bond_uses_the_custom_mm_size(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert build_print_settings(PrintOptions(paper="long-bond")) == (
            "paper=215.9mm x 330.2mm,fit"
        )

    def test_config_paper_size_is_the_fallback(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "letter")
        assert build_print_settings(PrintOptions()) == "paper=letter,fit"

    def test_request_paper_overrides_config(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "a4")
        assert build_print_settings(PrintOptions(paper="legal")) == "paper=legal,fit"

    def test_copies_multiply_and_collate(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert build_print_settings(PrintOptions(copies=3)) == "3x,collate"

    def test_pages_pass_through_verbatim(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert build_print_settings(PrintOptions(pages="2-6")) == "2-6"

    def test_monochrome_token(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        assert (
            build_print_settings(PrintOptions(color_mode="monochrome"))
            == "monochrome"
        )

    def test_full_combination(self, monkeypatch):
        monkeypatch.setattr(windows, "PAPER_SIZE", "")
        options = PrintOptions(
            copies=2, pages="2-6", paper="letter", color_mode="monochrome"
        )
        assert build_print_settings(options) == (
            "paper=letter,fit,2x,collate,2-6,monochrome"
        )


class TestPaperKeyConsistency:
    def test_every_choice_has_a_layout_and_an_engine_token(self):
        # One list of paper keys feeds validation (models), page layout
        # (processors/base) and the print engine (windows) — a drift here
        # would let a validated paper produce no layout or no token.
        for key in PAPER_CHOICES:
            if key == "":
                continue
            assert key in processor_base.PAGE_SIZES_PT
            assert key in windows.PAPER_TOKENS
