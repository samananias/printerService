"""Unit tests for the processor registry (app/processors).

Phase 1 registers exactly one processor: the PDF pass-through. These tests
pin the registry contract the later phases plug into:
  - for_category() returns a processor whose process() yields a PDF path;
  - unregistered categories return None — the "not enabled yet" signal the
    upload gate and the pipeline both rely on.
"""

from app.processors import for_category, supported_categories


class TestRegistry:
    def test_pdf_category_has_a_processor(self):
        assert for_category("pdf") is not None

    def test_future_categories_are_not_registered_yet(self):
        # Phase order from docs/MULTI_FORMAT_PLAN.md §10: images (p11),
        # office (p12), text (p13). Each phase extends this expectation.
        assert for_category("image") is None
        assert for_category("office") is None
        assert for_category("text") is None

    def test_unknown_category_returns_none(self):
        assert for_category("holodeck") is None

    def test_supported_categories_are_pinned_for_phase_1(self):
        assert supported_categories() == ("pdf",)


class TestPdfProcessor:
    def test_process_returns_the_source_unchanged(self, tmp_path):
        src = tmp_path / "doc.pdf"
        src.write_bytes(b"%PDF-1.4 test")

        result = for_category("pdf").process(src, tmp_path)

        assert result == src  # pass-through: same path, nothing new written
        assert src.read_bytes() == b"%PDF-1.4 test"  # source untouched
