"""
spike_scan.py — Scan Feature Spike (docs/SCAN_PLAN.md §8 Phase 0, S1–S4)

Run this ON the print-server PC, from the project root:

    .venv\\Scripts\\python spike_scan.py

(No extra installs — pywin32 and Pillow ship in requirements.txt.)

Covers the four scan spikes (SCAN_PLAN §8 Phase 0). Like T1–T7: hardware
truth before code — this script decides whether the scan feature proceeds
to Phase 1.

  S1 — Detection. Enumerate Windows' WIA device list; the L3210 must
       appear with Type == 1 (scanner). Then, to prove the "no scanner
       must not affect anything" requirement, UNPLUG the printer's USB
       and re-run: detection must degrade to a clean empty result, not a
       crash.
  S2 — Single scan. Transfer one flatbed page to PNG. PASS = a real,
       legible image file is produced.
  S3 — PDF wrap. Feed S2's PNG through the REAL ImageProcessor — the
       exact production path Phase 2 will reuse (same way T7 used the
       real TextProcessor). PASS = a valid single-page PDF that opens
       correctly. (Optionally printed for the paper smile-check.)
  S4 — Concurrent-with-print sanity check. A scan and a print run at the
       same time over the same USB cable (different Windows subsystems,
       but one physical unit). PASS = both succeed.

PASS criteria — judge with your eyes where the script cannot see:
  [ ] S2: the PNG on screen is a legible scan of the page on the glass
  [ ] S3: the PDF opens; the page is correctly oriented, nothing clipped
  [ ] S4: paper comes out AND the scan file is complete/legible
Record the results in SCAN_PLAN §10 (like T4–T7 in SOURCE_OF_TRUTH §5) —
they are the Phase 0 acceptance gate.

Technical note (SCAN_PLAN §0, adjustment 1): WIA format IDs are passed as
GUID strings — win32com.client.constants needs a makepy-generated module
and must not be relied on.
"""

import argparse
import itertools
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

LINE = "=" * 64

# WIA constants, passed as raw values so no generated (makepy) constants
# module is ever needed (see module docstring / SCAN_PLAN §0).
WIA_SCANNER_TYPE = 1  # DeviceInfo.Type: 1 = scanner, 2 = camera, 3 = video
WIA_FORMAT_PNG = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"

# Unique names per transfer: S4 rescans while S2's file is still in the
# same temp dir, and WIA's ImageFile.SaveFile REFUSES to overwrite
# (COM error 0x80070050 ERROR_ALREADY_EXISTS — the original S4 FAIL).
_SCAN_SEQ = itertools.count(1)


def banner(text: str) -> None:
    print("\n" + LINE)
    print(text)
    print(LINE)


def _prop(obj, name: str, default="?"):
    """Read a WIA property by name, never raising (spike = diagnostics)."""
    try:
        return obj.Properties(name).Value
    except Exception:
        return default


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


# ---------------------------------------------------------------------------
# S1 — detection (the spike that guards the whole feature)
# ---------------------------------------------------------------------------


def s1_detect() -> tuple[bool, str]:
    """Enumerate WIA devices. Returns (scanner_found, detail).

    NEVER raises — any COM/WIA failure is reported as "no scanner", which
    is exactly the behavior the production list_scan_devices() must have
    (SCAN_PLAN §3.2). This function is the template for it.
    """
    try:
        import win32com.client
    except ImportError as exc:
        return False, f"pywin32 not importable ({exc}) — treated as no scanner"

    try:
        manager = win32com.client.Dispatch("WIA.DeviceManager")
        infos = manager.DeviceInfos
        count = infos.Count
    except Exception as exc:
        return False, f"WIA enumeration failed ({exc}) — treated as no scanner"

    if count == 0:
        return False, "WIA sees no imaging devices (clean empty result, no crash)"

    print(f"\n  WIA devices found: {count}")
    scanners = []
    for index in range(1, count + 1):  # WIA collections are 1-based
        try:
            info = infos.Item(index)
        except Exception as exc:
            print(f"  device {index}: unreadable ({exc})")
            continue
        name = _prop(info, "Name")
        try:
            device_type = info.Type
        except Exception:
            device_type = "?"
        marker = "  <== SCANNER" if device_type == WIA_SCANNER_TYPE else ""
        print(f"  [{index}] name={name!r} type={device_type}{marker}")
        if device_type == WIA_SCANNER_TYPE:
            scanners.append(info)

    if not scanners:
        return False, (
            "devices present but none with Type == 1 "
            "(e.g. only a webcam) — clean 'not a scanner' result"
        )

    names = [_prop(s, "Name") for s in scanners]
    matched = any("L3210" in str(name) for name in names)
    return True, f"scanner(s): {names} (L3210 match: {matched})"


def connect_first_scanner():
    """Connect to the first WIA scanner and pick a transferable flatbed item.

    Returns (device, item, item_description). Raises RuntimeError with a
    phone-user-readable message if nothing works — the same message shape
    the scan pipeline will map to a failed job.
    """
    import win32com.client

    manager = win32com.client.Dispatch("WIA.DeviceManager")
    infos = manager.DeviceInfos
    last_error = "no scanner found"
    for index in range(1, infos.Count + 1):
        try:
            info = infos.Item(index)
            if info.Type != WIA_SCANNER_TYPE:
                continue
            device = info.Connect()
        except Exception as exc:
            last_error = f"could not connect to scanner {index}: {exc}"
            continue
        try:
            items = device.Items
            item_count = items.Count
        except Exception as exc:
            last_error = f"connected but no items: {exc}"
            continue
        print(f"  device items: {item_count}")
        for item_index in range(1, item_count + 1):
            try:
                item = items.Item(item_index)
            except Exception:
                continue
            item_name = _prop(item, "Item Name", f"item {item_index}")
            print(f"    [{item_index}] {item_name}")
        # Flatbed-first: prefer an item that is NOT the feeder. On the
        # L3210 (flatbed-only) item 1 is the flatbed; on multi-item
        # devices the flatbed usually names itself "Flatbed".
        order = sorted(
            range(1, item_count + 1),
            key=lambda i: "flat" not in _prop(items.Item(i), "Item Name", "").lower(),
        )
        for item_index in order:
            item = items.Item(item_index)
            # Best-effort: force the flatbed source where the driver
            # offers it (WIA_DPS_DOCUMENT_HANDLING_SELECT = FLATBED).
            try:
                item.Properties("Document Handling Select").Value = 1
            except Exception:
                pass  # flatbed-only, or driver not exposing the property
            return device, item, _prop(item, "Item Name", f"item {item_index}")
        last_error = "scanner connected but no transferable item"
    raise RuntimeError(last_error)


def s2_scan_png(out_dir: Path, dpi: int) -> tuple[Path, float]:
    """Transfer one flatbed page to PNG via WIA. Returns (path, seconds)."""
    _, item, item_name = connect_first_scanner()
    print(f"  transferring from: {item_name}")

    # Best-effort resolution set — the driver may refuse (then its default
    # is used and the spike still tells us the scan works).
    for prop_name in ("Horizontal Resolution", "Vertical Resolution"):
        try:
            item.Properties(prop_name).Value = dpi
        except Exception as exc:
            print(f"  note: could not set {prop_name} to {dpi} ({exc})")

    start = time.monotonic()
    image = item.Transfer(WIA_FORMAT_PNG)
    out_path = out_dir / f"scan_{dpi}dpi_{next(_SCAN_SEQ):02d}.png"
    image.SaveFile(str(out_path))
    elapsed = time.monotonic() - start
    return out_path, elapsed


# ---------------------------------------------------------------------------
# S3 — PDF wrap (the REAL production path: ImageProcessor)
# ---------------------------------------------------------------------------


def s3_wrap_pdf(png_path: Path, out_dir: Path) -> Path:
    from app.processors.images import IMAGE_PROCESSOR

    return IMAGE_PROCESSOR.process(png_path, out_dir)


# ---------------------------------------------------------------------------
# Print helpers (T7 convention — the service's exact SumatraPDF invocation)
# ---------------------------------------------------------------------------


def make_print_pdf(out_dir: Path) -> Path:
    """A one-page test document via the REAL TextProcessor."""
    from app.processors.text import TextProcessor

    source = out_dir / "s4_test_page.txt"
    source.write_text(
        "S4 concurrent spike — this page printed WHILE a scan ran\n"
        "on the same USB-connected Epson L3210.\n\n"
        "If you are reading this on paper, the print half of S4 survived.\n",
        encoding="utf-8",
    )
    return TextProcessor().process(source, out_dir)


def print_pdf(sumatra: str, pdf_path: Path, printer_name: str) -> None:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="scan resolution to request (default 200; DPI-allowlist input)",
    )
    parser.add_argument(
        "--no-print",
        action="store_true",
        help="skip the paper-touching parts (S3's optional print, all of S4)",
    )
    parser.add_argument(
        "--only",
        choices=("s1", "s2", "s3", "s4"),
        default=None,
        help="run a single spike (default: all; S1 always runs as the gate)",
    )
    args = parser.parse_args()

    banner("SCAN SPIKE (S1–S4) — run this ON the PC the printer is plugged into")
    results: list[tuple[str, str, str]] = []

    try:
        from app.printer.windows import find_sumatra

        sumatra = find_sumatra()
    except ImportError as exc:
        print(f"Cannot import the app ({exc}). Run from the project root:")
        print("    .venv\\Scripts\\python spike_scan.py")
        return 1

    printer_name = None
    if not args.no_print:
        try:
            import win32print  # noqa: F401  (pywin32 presence check, like T1)

            printer_name = find_printer()
        except ImportError:
            print("pywin32 is not installed here:  pip install pywin32")
            return 1

    # ---------------- S1: detection ----------------
    banner("S1 — DETECTION (WIA device enumeration; must never crash)")
    found, detail = s1_detect()
    # A clean empty result is a PASS on the unplugged re-run — the whole
    # point of S1's second run — so the summary must not label it FAIL.
    expected_empty = not found and ("clean" in detail or "not a scanner" in detail)
    results.append(
        (
            "S1 detection",
            "PASS" if (found or expected_empty) else "FAIL",
            detail
            + (
                ""
                if found
                else " — clean empty result IS the pass (USB unplugged: "
                "no scanner, no crash, no effect on anything)"
            ),
        )
    )
    print(f"\n  -> {detail}")
    if not found:
        print(
            "\n  If the printer IS plugged in, this is the bug to investigate.\n"
            "  If the USB is UNPLUGGED, this clean empty result is exactly the\n"
            "  S1 PASS the plan asks for: detection degrades, nothing crashes.\n"
            "  (S2–S4 need the scanner, so they are skipped.)"
        )
        _summary(results)
        return 0 if expected_empty else 2

    temp_dir = Path(tempfile.mkdtemp(prefix="spike_scan_"))
    try:
        # ---------------- S2: single scan ----------------
        png_path = None
        if args.only not in (None, "s2"):
            results.append(
                ("S2 single scan", "SKIP", f"skipped (--only {args.only})")
            )
        else:
            banner(f"S2 — SINGLE SCAN (flatbed -> PNG @ {args.dpi} dpi requested)")
            print(">>> Put a page FACE DOWN on the scanner glass.")
            input("Press Enter when ready...")
            try:
                png_path, elapsed = s2_scan_png(temp_dir, args.dpi)
                size_kb = png_path.stat().st_size / 1024
                results.append(
                    (
                        "S2 single scan",
                        "PASS" if size_kb > 10 else "WARN",
                        f"{png_path.name}: {size_kb:.0f} KB in {elapsed:.1f}s "
                        f"-> {png_path} (EYES: legible?)",
                    )
                )
            except Exception as exc:
                results.append(("S2 single scan", "FAIL", str(exc)))

        # ---------------- S3: PDF wrap ----------------
        banner("S3 — PDF WRAP (S2's PNG through the REAL ImageProcessor)")
        if png_path is None:
            results.append(("S3 PDF wrap", "SKIP", "no S2 image to wrap"))
        elif args.only not in (None, "s3"):
            results.append(
                ("S3 PDF wrap", "SKIP", f"skipped (--only {args.only})")
            )
        else:
            try:
                start = time.monotonic()
                pdf_path = s3_wrap_pdf(png_path, temp_dir)
                elapsed = time.monotonic() - start
                magic_ok = pdf_path.read_bytes()[:5] == b"%PDF-"
                size_kb = pdf_path.stat().st_size / 1024
                results.append(
                    (
                        "S3 PDF wrap",
                        "PASS" if magic_ok else "FAIL",
                        f"{pdf_path.name}: {size_kb:.0f} KB in {elapsed:.1f}s, "
                        f"%PDF- magic: {magic_ok} -> {pdf_path}",
                    )
                )
                if magic_ok and not args.no_print and sumatra and printer_name:
                    answer = input(
                        "\n  Print the wrapped PDF for the paper smile-check? [y/N] "
                    )
                    if answer.strip().lower() == "y":
                        try:
                            print_pdf(sumatra, pdf_path, printer_name)
                            print("  print accepted — CHECK PAPER (upright, unclipped)")
                        except Exception as exc:
                            print(f"  print FAILED: {exc}")
            except Exception as exc:
                results.append(("S3 PDF wrap", "FAIL", str(exc)))

        # ---------------- S4: concurrent scan + print ----------------
        if args.only not in (None, "s4"):
            results.append(
                ("S4 concurrent", "SKIP", f"skipped (--only {args.only})")
            )
        elif args.no_print or not (sumatra and printer_name):
            results.append(
                ("S4 concurrent", "SKIP", "skipped (--no-print or no print engine)")
            )
        else:
            _s4_concurrent(args, temp_dir, sumatra, printer_name, results)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    _summary(results)
    return 0 if all(r[1] in ("PASS", "WARN", "SKIP") for r in results) else 2


def _s4_concurrent(args, temp_dir, sumatra, printer_name, results) -> None:
    """S4: a scan and a print at the same time over the one USB cable.

    The print runs in a helper thread (subprocess only — never COM, which
    stays on the main thread here); the scan runs on the main thread. Both
    results are reported independently so one failure doesn't hide the other.
    """
    banner(
        "S4 — CONCURRENT SCAN + PRINT (one USB cable, two subsystems)\n"
        ">>> Leave the SAME page on the glass. A test page will print\n"
        ">>> WHILE the scan runs."
    )
    input("Press Enter when ready...")
    try:
        test_pdf = make_print_pdf(temp_dir)
        print_error: list[str] = []
        print_done = threading.Event()

        def _print_job() -> None:
            # Only subprocess + file I/O here — no COM in this thread.
            try:
                print_pdf(sumatra, test_pdf, printer_name)
            except Exception as exc:  # captured, reported after join
                print_error.append(str(exc))
            finally:
                print_done.set()

        printer_thread = threading.Thread(
            target=_print_job, name="s4-print", daemon=True
        )
        printer_thread.start()
        try:
            scan_path, scan_seconds = s2_scan_png(temp_dir, args.dpi)
        finally:
            printer_thread.join(timeout=200)

        scan_size_kb = scan_path.stat().st_size / 1024
        if print_error:
            results.append(("S4 concurrent", "FAIL", f"print: {print_error[0]}"))
        elif not print_done.is_set():
            results.append(("S4 concurrent", "FAIL", "print thread timed out"))
        else:
            results.append(
                (
                    "S4 concurrent",
                    "PASS",
                    f"scan {scan_size_kb:.0f} KB in {scan_seconds:.1f}s "
                    "AND print accepted — CHECK BOTH (paper out, PNG legible)",
                )
            )
    except Exception as exc:
        results.append(("S4 concurrent", "FAIL", str(exc)))


def _summary(results: list[tuple[str, str, str]]) -> None:
    banner("SUMMARY")
    for name, status, detail in results:
        print(f"[{status:4}] {name}: {detail}")
    print(
        "\nNow judge what the script cannot see:\n"
        "  [ ] S2: the PNG is a legible scan of the page on the glass\n"
        "  [ ] S3: the PDF opens; page upright, nothing clipped\n"
        "  [ ] S4: paper came out AND the scan file is complete\n"
        "\nRecord the results in SCAN_PLAN §10 (like T4–T7 in SOURCE_OF_TRUTH\n"
        "§5) — they are the Phase 0 acceptance gate before any scan code."
    )


if __name__ == "__main__":
    sys.exit(main())
