"""Image processor (Phase 2) — turns images into print-ready PDF pages.

Strategy (docs/MULTI_FORMAT_PLAN.md §6): Pillow composites the picture onto
a white page canvas and saves the canvas as the PDF — one code path for
every input quirk:

    load → EXIF-rotate → flatten transparency onto white →
    fit + center on the page (wide photos rotate the PAGE, not the pixels)
    → cap the effective DPI → save (multi-frame files become multi-page PDFs)

Why a canvas instead of Pillow's bare img.save(..., "PDF"): the canvas
pins the PAGE size (A4 by default) no matter the photo's pixel size,
centers the picture with real margins, and caps the effective DPI — a
12 MP phone photo must not become a 100 MB PDF, and a 200 px thumbnail
must not be blown up into a full page of blur.

Quality decisions recorded in MULTI_FORMAT_PLAN.md §6 (images row + §7):
EXIF orientation is honored, transparency prints white (unflattened alpha
prints black on paper), a wide photo gets a landscape page instead of
rotated pixels (rotation would fight EXIF and resample the image twice).
"""

import logging
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from app.config import PAPER_SIZE
from app.processors.base import ConversionError

logger = logging.getLogger(__name__)

# Page sizes in points (1 pt = 1/72"). Unknown/empty PAPER_SIZE falls back
# to A4. Add entries (e.g. long bond 8.5x13) as later phases need them.
PAGE_SIZES_PT = {
    "a3": (842, 1191),
    "a4": (595, 842),
    "a5": (420, 595),
    "letter": (612, 792),
    "legal": (612, 1008),
}
DEFAULT_PAGE = "a4"

MARGIN_PT = 36    # 0.5" — this printer cannot print borderless anyway
MAX_DPI = 300     # above ~300 effective DPI, extra pixels are invisible on paper
SOURCE_DPI = 96   # small images are assumed ~96 DPI (the web/phone norm)...
MAX_UPSCALE = MAX_DPI / SOURCE_DPI  # ...so upscaling stops at 300 effective DPI
MAX_FRAMES = 10   # an animated WebP/scan-batch TIFF is not a 50-page print job


def page_size_pt() -> tuple[int, int]:
    """The page images are laid out on: PAPER_SIZE when it names a known
    size, A4 otherwise (images always need a concrete page to sit on)."""
    return PAGE_SIZES_PT.get(PAPER_SIZE.strip().lower(), PAGE_SIZES_PT[DEFAULT_PAGE])


def layout(
    img_w: int, img_h: int, page_pt: tuple[int, int]
) -> tuple[tuple[int, int], tuple[int, int, int, int]]:
    """Fit an image on a page; return ((canvas_w, canvas_h), (x, y, w, h)).

    Pure geometry — all values in CANVAS pixels, and the canvas renders at
    MAX_DPI (so a page of `page_pt` points becomes page_pt * MAX_DPI/72
    pixels). Rules:

    - a wide image on a portrait page rotates the PAGE, not the pixels;
    - the image never leaves the printable area (page minus margins);
    - upscaling is capped at MAX_UPSCALE: a small image prints near its
      natural size, centered, instead of stretched full-page blurry.
    """
    page_w, page_h = page_pt
    if img_w > img_h and page_w < page_h:
        page_w, page_h = page_h, page_w

    points_to_px = MAX_DPI / 72
    canvas_w, canvas_h = round(page_w * points_to_px), round(page_h * points_to_px)
    margin_px = round(MARGIN_PT * points_to_px)
    avail_w, avail_h = canvas_w - 2 * margin_px, canvas_h - 2 * margin_px

    scale = min(avail_w / img_w, avail_h / img_h, MAX_UPSCALE)
    box_w, box_h = max(1, round(img_w * scale)), max(1, round(img_h * scale))
    x, y = (canvas_w - box_w) // 2, (canvas_h - box_h) // 2
    return (canvas_w, canvas_h), (x, y, box_w, box_h)


def _printable(img: Image.Image) -> Image.Image:
    """EXIF-rotate, then flatten anything with transparency onto white.

    Returns a plain RGB image — the only mode worth encoding into a PDF
    page for this printer.
    """
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        if "A" in img.getbands() or img.mode == "P":
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            return flat
        return img.convert("RGB")
    return img


def _page_canvas(img: Image.Image) -> Image.Image:
    """One print-ready page: the image fitted and centered on white."""
    (canvas_w, canvas_h), (x, y, box_w, box_h) = layout(
        img.width, img.height, page_size_pt()
    )
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    canvas.paste(img.resize((box_w, box_h), Image.Resampling.LANCZOS), (x, y))
    return canvas


class ImageProcessor:
    def available(self) -> bool:
        # Pillow is a hard dependency (requirements.txt) — always available.
        return True

    def process(self, src: Path, out_dir: Path) -> Path:
        """Convert an image file into the print-ready PDF the engine gets."""
        pdf_path = out_dir / f"{src.stem}.pdf"
        try:
            frames: list[Image.Image] = []
            with Image.open(src) as img:
                for frame in ImageSequence.Iterator(img):
                    frames.append(_page_canvas(_printable(frame)))
                    if len(frames) > MAX_FRAMES:
                        raise ConversionError(
                            f"The image has more than {MAX_FRAMES} frames; the "
                            f"service prints at most {MAX_FRAMES} pages from one "
                            "image file. Split it or export single pages."
                        )
            if not frames:
                raise ConversionError("The image contains no frames to print.")
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(
                f"Could not read the image — it looks corrupt or is an "
                f"unsupported image format ({exc})"
            ) from exc

        try:
            first, *rest = frames
            first.save(
                pdf_path,
                "PDF",
                resolution=MAX_DPI,
                save_all=bool(rest),
                append_images=rest,
            )
        except OSError as exc:
            raise ConversionError(f"Could not write the print file: {exc}") from exc

        logger.info(
            "converted %s -> %s (%d page(s))", src.name, pdf_path.name, len(frames)
        )
        return pdf_path


# Stateless → one shared instance for every job.
IMAGE_PROCESSOR = ImageProcessor()
