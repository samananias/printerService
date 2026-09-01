"""
spike_t7_text.py — Text/CSV Printing Spike (docs/MULTI_FORMAT_PLAN.md §14, T7)

Run this ON the print-server PC, from the project root:

    .venv\\Scripts\\python spike_t7_text.py

(No extra installs — reportlab ships in requirements.txt.)

Generates a TXT and a CSV, converts each with the service's REAL
TextProcessor (reportlab — the exact production path), prints the PDFs via
SumatraPDF, and reports page counts:

  1. TXT — paragraphs + lines much longer than the page width
           (word-wrap must keep everything inside the margins)
  2. CSV — 40 rows x 6 columns with quoted cells containing commas
           (grid must stay aligned, header repeated on page 2)

PASS criteria — judge the PAPER (the script cannot see it):
  [ ] TXT: nothing clipped at either margin, no orphan single words
      making a mess, readable monospace
  [ ] CSV: all 6 columns visible with borders, nothing cut to "...",
      header row repeated on every page
  [ ] conversion was instant (text should print with no wait at all)
Record the summary in SOURCE_OF_TRUTH Section 5, like the T4/T5/T6
entries. These results are the Phase 4 acceptance gate — the last one
before the whole MVP format set is verified on real paper.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
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


def make_test_files(folder: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []

    # 1. TXT — short lines, plus lines far wider than the page (the wrap
    #    check), plus an empty-line rhythm.
    prose = [
        "T7 text spike — TXT rendering check",
        "",
        "The next line is a single unbroken stream far wider than the page:",
        "word " * 60,
        "Then normal paragraphs resume. " * 3,
        "Final line of page one, hopefully.",
        "",
    ] * 15
    path = folder / "t7_1_notes.txt"
    path.write_text("\n".join(prose), encoding="utf-8")
    out.append(("1 TXT (wrap + pagination)", path))

    # 2. CSV — quoted cells containing commas, 40 rows x 6 columns (multi-
    #    page grid with a repeated header).
    rows = ["item,qty,unit price,location,checked by,remark"]
    for number in range(1, 41):
        rows.append(
            f'"widget {number}, type A",{number},9.99,shelf {number % 7},'
            f'"crew, night shift",ok'
        )
    path = folder / "t7_2_inventory.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    out.append(("2 CSV (40x6 grid, quoted cells)", path))

    return out


def print_pdf(sumatra: str, pdf_path: Path, printer_name: str) -> None:
    """The service's exact print invocation (see app/printer/windows.py)."""
    result = subprocess.run(
        [sumatra, "-print-to", printer_name, "-silent", str(pdf_path)],
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SumatraPDF exited with code {result.returncode}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    banner("T7 TEXT SPIKE — run this ON the PC the printer is plugged into")

    try:
        from app.printer.windows import find_sumatra
        from app.processors.text import TextProcessor
    except ImportError as exc:
        print(f"Cannot import the app ({exc}). Run from the project root:")
        print("    .venv\\Scripts\\python spike_t7_text.py")
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

    processor = TextProcessor()
    temp_dir = Path(tempfile.mkdtemp(prefix="spike_t7_"))
    results: list[tuple[str, str, str]] = []
    try:
        for name, file_path in make_test_files(temp_dir):
            try:
                pdf_path = processor.process(file_path, temp_dir)
                print_pdf(sumatra, pdf_path, printer_name)
                results.append(
                    (f"T7 {name}", "PASS", "print accepted — CHECK PAPER")
                )
            except Exception as exc:
                results.append((f"T7 {name}", "FAIL", str(exc)))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    banner("SUMMARY")
    for name, status, detail in results:
        print(f"[{status:4}] {name}: {detail}")

    print(
        "\nNow judge the paper:\n"
        "  [ ] TXT: nothing clipped at either margin; wrapping is clean\n"
        "  [ ] CSV: all 6 columns visible, borders drawn, no '...' cuts\n"
        "  [ ] CSV: header row repeated on page 2\n"
        "\nRecord the results in SOURCE_OF_TRUTH Section 5 (like the T4/T5/T6\n"
        "entries) — they are the Phase 4 acceptance gate. With this pass, the\n"
        "whole MVP format set is verified on real paper."
    )
    return 0 if all(r[1] == "PASS" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
