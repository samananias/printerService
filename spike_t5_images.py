"""
spike_t5_images.py — Image Printing Spike (docs/MULTI_FORMAT_PLAN.md §14, T5)

Run this ON the print-server PC, from the project root:

    .venv\\Scripts\\pip install pillow
    .venv\\Scripts\\python spike_t5_images.py [--paper A4]

Uses the service's REAL image processor (app/processors/images.py) to
convert generated test images into PDFs, then prints them via SumatraPDF
exactly like the service does, timing each step:

  1. JPEG — photo-like gradient          (portrait page)
  2. PNG  — with transparency            (corners must print WHITE, not black)
  3. WebP — the modern web format
  4. JPEG — with EXIF rotation           (must come out upright, matching #1)

With --paper A4|letter|legal|a5|a3, one extra copy of image 1 is printed
with -print-settings "paper=<X>,fit" to check the Epson driver honors the
paper size (plan assumption #3) BEFORE setting PAPER_SIZE in .env.

PASS criteria — judge the PAPER (the script cannot see it):
  [ ] every page upright, nothing clipped, even white margins
  [ ] image 2's corners white, not black
  [ ] image 4 upright (EXIF respected — same orientation as image 1)
  [ ] --paper copy actually matches the requested paper size
Record the summary in SOURCE_OF_TRUTH Section 5, like the T4 entry.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LINE = "=" * 64


def banner(text: str) -> None:
    print("\n" + LINE)
    print(text)
    print(LINE)


def find_printer() -> str:
    """Prefer the L3210 by name, fall back to the Windows default."""
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = sorted(p[2] for p in win32print.EnumPrinters(flags))
    if not names:
        raise RuntimeError("No printers found — is the Epson installed on this PC?")
    for name in names:
        if "L3210" in name:
            return name
    return names[0]


def make_test_images(folder: Path) -> list[tuple[str, Path]]:
    """Generate the four spike images (no binary fixtures in the repo)."""
    from PIL import Image, ImageDraw

    # A smooth color gradient, built small and resized (fast, looks like a
    # photo's tonal range on paper).
    small = Image.new("RGB", (12, 16))
    for y in range(16):
        for x in range(12):
            small.putpixel((x, y), (x * 255 // 11, y * 255 // 15, 128))
    gradient = small.resize((1200, 1600), Image.Resampling.LANCZOS)

    out: list[tuple[str, Path]] = []

    path = folder / "t5_1_gradient.jpg"
    gradient.save(path, quality=90)
    out.append(("1 JPEG gradient (portrait)", path))

    # Transparent background + opaque circle: the corners must print WHITE.
    rgba = Image.new("RGBA", (800, 800), (255, 0, 0, 0))
    draw = ImageDraw.Draw(rgba)
    draw.ellipse((100, 100, 700, 700), fill=(0, 0, 255, 255))
    path = folder / "t5_2_alpha.png"
    rgba.save(path)
    out.append(("2 PNG with transparency", path))

    path = folder / "t5_3_modern.webp"
    gradient.save(path, quality=90)
    out.append(("3 WebP", path))

    # Same gradient WITH an EXIF orientation tag: must print like image 1,
    # not rotated 90°.
    exif = Image.Exif()
    exif[274] = 6  # orientation: rotate 90° to display upright
    path = folder / "t5_4_exif.jpg"
    gradient.save(path, quality=90, exif=exif)
    out.append(("4 JPEG with EXIF rotation", path))

    return out


def print_pdf(
    sumatra: str, pdf_path: Path, printer_name: str, settings: str | None = None
) -> None:
    """The service's exact print invocation (see app/printer/windows.py)."""
    cmd = [sumatra, "-print-to", printer_name]
    if settings:
        cmd += ["-print-settings", settings]
    cmd += ["-silent", str(pdf_path)]
    result = subprocess.run(cmd, capture_output=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(
            f"SumatraPDF exited with code {result.returncode}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper",
        choices=["a4", "letter", "legal", "a5", "a3"],
        type=str.lower,
        help="also print one copy with -print-settings paper=<X>,fit",
    )
    args = parser.parse_args()

    banner("T5 IMAGE SPIKE — run this ON the PC the printer is plugged into")

    try:
        from app.printer.windows import find_sumatra
        from app.processors.images import ImageProcessor
    except ImportError as exc:
        print(f"Cannot import the app ({exc}). Run from the project root:")
        print("    .venv\\Scripts\\python spike_t5_images.py")
        return 1

    try:
        import win32print  # noqa: F401  (pywin32 presence check, like T1)
    except ImportError:
        print("pywin32 is not installed here:  pip install pywin32")
        return 1

    printer_name = find_printer()
    sumatra = find_sumatra()
    if not sumatra:
        print("SumatraPDF not found — install it or set SUMATRA_PATH in .env")
        return 1

    print(f"\nPrinter:  {printer_name}")
    print(f"Sumatra:  {sumatra}")
    print("\n>>> Keep paper loaded and watch the physical printer.")
    input("Press Enter when ready...")

    processor = ImageProcessor()
    temp_dir = Path(tempfile.mkdtemp(prefix="spike_t5_"))
    results: list[tuple[str, str, str]] = []
    try:
        for name, image_path in make_test_images(temp_dir):
            try:
                started = time.perf_counter()
                pdf_path = processor.process(image_path, temp_dir)
                seconds = time.perf_counter() - started
                print_pdf(sumatra, pdf_path, printer_name)
                results.append(
                    (
                        f"T5 {name}",
                        "PASS",
                        f"converted in {seconds:.2f}s, print accepted — CHECK PAPER",
                    )
                )
            except Exception as exc:
                results.append((f"T5 {name}", "FAIL", str(exc)))

        if args.paper:
            try:
                pdf_path = processor.process(temp_dir / "t5_1_gradient.jpg", temp_dir)
                print_pdf(sumatra, pdf_path, printer_name, f"paper={args.paper},fit")
                results.append(
                    (
                        f"T5 paper={args.paper} via -print-settings",
                        "PASS",
                        "print accepted — verify the paper size matches on paper",
                    )
                )
            except Exception as exc:
                results.append(
                    (f"T5 paper={args.paper} via -print-settings", "FAIL", str(exc))
                )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    banner("SUMMARY")
    for name, status, detail in results:
        print(f"[{status:4}] {name}: {detail}")

    print(
        "\nNow judge the paper:\n"
        "  [ ] all pages upright, nothing clipped, even white margins\n"
        "  [ ] image 2's corners WHITE (black = alpha flattening bug)\n"
        "  [ ] image 4 upright, same orientation as image 1 (EXIF works)\n"
        + (
            f"  [ ] --paper {args.paper} copy really is {args.paper} size\n"
            if args.paper
            else ""
        )
        + "\nRecord the results in SOURCE_OF_TRUTH Section 5 (like the T4 entry) —\n"
        "they are the Phase 2 acceptance gate (docs/MULTI_FORMAT_PLAN.md §14)."
    )
    return 0 if all(r[1] == "PASS" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
