"""Unit tests for the image processor (app/processors/images.py).

The processor composites each frame onto a white page canvas and saves the
canvas as the PDF page. The geometry is pure math (layout()), so the
fit/center/orientation rules are asserted exactly; the PDF bytes themselves
are only checked structurally (%PDF- magic, source untouched) — reading
pages back would need another PDF library, and the plan says avoid
unnecessary dependencies. Paper-level quality (transparency white, EXIF
upright, nothing clipped) is spike T5's job on real hardware.
"""

import pytest
from PIL import Image

from app.processors import base as processor_base
from app.processors import images
from app.processors.base import ConversionError, page_size_pt
from app.processors.images import MAX_UPSCALE, ImageProcessor, layout

A4_PT = (595, 842)


class TestLayout:
    def test_portrait_photo_fits_the_printable_area_centered(self):
        canvas = (round(595 * 300 / 72), round(842 * 300 / 72))  # A4 at 300 DPI
        (canvas_w, canvas_h), (x, y, box_w, box_h) = layout(3000, 4000, A4_PT)

        assert (canvas_w, canvas_h) == canvas
        margin = round(36 * 300 / 72)  # 150 px
        assert box_w <= canvas_w - 2 * margin  # inside the margins
        assert box_h <= canvas_h - 2 * margin
        assert abs((canvas_w - box_w) - 2 * x) <= 1  # centered (±1 px rounding)
        assert abs((canvas_h - box_h) - 2 * y) <= 1

    def test_wide_photo_rotates_the_page_not_the_pixels(self):
        # A landscape photo gets a landscape canvas — rotating the pixels
        # would fight EXIF orientation and resample the image a second time.
        (canvas_w, canvas_h), _ = layout(4000, 3000, A4_PT)
        assert canvas_w > canvas_h

    def test_small_images_upscale_is_capped(self):
        # A 200 px thumbnail must not be blown up to full-page blur: the
        # upscale stops at MAX_UPSCALE (= 300 effective DPI from 96).
        _, (_, _, box_w, _) = layout(200, 100, A4_PT)
        assert box_w == round(200 * MAX_UPSCALE)


class TestPageSize:
    def test_empty_and_unknown_config_fall_back_to_a4(self, monkeypatch):
        for value in ("", "bogus"):
            monkeypatch.setattr(processor_base, "PAPER_SIZE", value)
            assert page_size_pt() == (595, 842)

    def test_known_names_are_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(processor_base, "PAPER_SIZE", "Letter")
        assert page_size_pt() == (612, 792)


class TestPrintable:
    def test_alpha_is_flattened_onto_white_not_black(self):
        # Fully transparent red pixels: the printer has no "transparent
        # paper", so unflattened alpha would print as black.
        rgba = Image.new("RGBA", (4, 4), (255, 0, 0, 0))

        flat = images._printable(rgba)

        assert flat.mode == "RGB"
        assert flat.getpixel((0, 0)) == (255, 255, 255)

    def test_exif_orientation_is_applied(self, tmp_path):
        wide = Image.new("RGB", (20, 10), "red")
        exif = Image.Exif()
        exif[274] = 6  # orientation tag: display rotated 90°
        path = tmp_path / "phone_photo.jpg"
        wide.save(path, exif=exif)

        with Image.open(path) as img:
            assert images._printable(img).size == (10, 20)  # dimensions swapped

    def test_plain_rgb_needs_no_flattening(self):
        assert images._printable(Image.new("RGB", (3, 3), "blue")).mode == "RGB"


class TestProcess:
    def test_jpeg_becomes_a_pdf_next_to_the_source(self, tmp_path):
        src = tmp_path / "job-1.jpg"
        Image.new("RGB", (40, 30), "green").save(src)

        pdf = ImageProcessor().process(src, tmp_path)

        assert pdf == tmp_path / "job-1.pdf"  # <job_id>.pdf, per the pipeline
        assert pdf.read_bytes().startswith(b"%PDF-")
        assert src.read_bytes().startswith(b"\xff\xd8")  # source untouched

    def test_corrupt_image_raises_a_human_error(self, tmp_path):
        src = tmp_path / "job-2.png"
        src.write_bytes(b"definitely not image data")

        with pytest.raises(ConversionError, match="corrupt"):
            ImageProcessor().process(src, tmp_path)

    def test_multipage_tiff_becomes_a_multipage_pdf(self, tmp_path):
        frames = [Image.new("RGB", (30, 20), color) for color in ("red", "green", "blue")]
        src = tmp_path / "job-3.tif"
        frames[0].save(src, save_all=True, append_images=frames[1:])

        pdf = ImageProcessor().process(src, tmp_path)

        assert pdf.read_bytes().startswith(b"%PDF-")

    def test_too_many_frames_are_refused_before_memory_blows_up(self, tmp_path):
        # An animated GIF with more frames than MAX_FRAMES must fail fast —
        # the guard fires DURING frame collection, not after rendering all
        # of them into canvases on a 4 GB PC. Frames differ per color
        # because GIF writers optimize identical frames away.
        frames = [
            Image.new("RGB", (2, 2), (number, 0, 0))
            for number in range(images.MAX_FRAMES + 1)
        ]
        src = tmp_path / "job-4.gif"
        frames[0].save(src, save_all=True, append_images=frames[1:])

        with pytest.raises(ConversionError, match="frames"):
            ImageProcessor().process(src, tmp_path)
