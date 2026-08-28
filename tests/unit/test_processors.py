"""Unit tests for the processor registry (app/processors).

These tests pin the registry contract the phases plug into:
  - for_category() returns a processor whose process() yields a PDF path;
  - unregistered categories return None — the "not enabled yet" signal the
    upload gate and the pipeline both rely on.
Phase 1 registered pdf, Phase 2 added image; office/text are still pending
(docs/MULTI_FORMAT_PLAN.md §10) and each later phase extends these
expectations.
"""


from app.processors import for_category, supported_categories


class TestRegistry:
    def test_registered_categories_have_processors(self):
        assert for_category("pdf") is not None
        assert for_category("image") is not None

    def test_future_categories_are_not_registered_yet(self):
        # Phase order from docs/MULTI_FORMAT_PLAN.md §10: office (p12),
        # text (p13).
        assert for_category("office") is None
        assert for_category("text") is None

    def test_unknown_category_returns_none(self):
        assert for_category("holodeck") is None

    def test_supported_categories_are_pinned_after_phase_2(self):
        assert supported_categories() == ("image", "pdf")


class TestPdfProcessor:
    def test_process_returns_the_source_unchanged(self, tmp_path):
        src = tmp_path / "doc.pdf"
        src.write_bytes(b"%PDF-1.4 test")

        result = for_category("pdf").process(src, tmp_path)

        assert result == src  # pass-through: same path, nothing new written
        assert src.read_bytes() == b"%PDF-1.4 test"  # source untouched


class TestImageProcessorRegistration:
    def test_image_processor_is_the_registered_instance(self):
        from app.processors.images import IMAGE_PROCESSOR

        assert for_category("image") is IMAGE_PROCESSOR
