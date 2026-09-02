"""Unit tests for app/models/scanning.py's scan-options validation
(docs/SCAN_PLAN.md §8 Phase 4). Strict allowlists — the same spirit as
validate_print_options (MULTI_FORMAT_PLAN.md §10): nothing invalid ever
reaches WIA.
"""

import pytest

from app.models.scanning import (
    DEFAULT_DPI,
    SCAN_COLOR_MODES,
    SCAN_DPI_CHOICES,
    SCAN_FORMATS,
    ScanOptions,
    validate_scan_options,
)


class TestValidateScanOptions:
    def test_defaults(self):
        assert validate_scan_options(200, "color", "pdf") == ScanOptions()

    def test_accepts_every_allowlisted_combination(self):
        for dpi in SCAN_DPI_CHOICES:
            for mode in SCAN_COLOR_MODES:
                for fmt in SCAN_FORMATS:
                    # Must not raise.
                    validate_scan_options(dpi, mode, fmt)

    def test_default_dpi_is_the_spike_verified_value(self):
        assert DEFAULT_DPI == 200

    def test_rejects_out_of_range_dpi(self):
        for bad in (0, 100, 400, -200, "fast"):
            with pytest.raises(ValueError, match="DPI"):
                validate_scan_options(bad, "color", "pdf")

    def test_rejects_unknown_color_mode(self):
        # "monochrome" is the PRINT side's name — scan uses "greyscale".
        with pytest.raises(ValueError, match="color"):
            validate_scan_options(200, "monochrome", "pdf")

    def test_rejects_unknown_format(self):
        with pytest.raises(ValueError, match="Format"):
            validate_scan_options(200, "color", "docx")

    def test_normalizes_case_and_whitespace(self):
        opts = validate_scan_options(300, "  GREYSCALE ", "PNG")
        assert opts == ScanOptions(dpi=300, color_mode="greyscale", format="png")
