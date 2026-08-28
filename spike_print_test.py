"""
spike_print_test.py — Printer Spike (README Section 9, Phase 4 "first experiment")

STANDALONE diagnostic script. Copy THIS ONE FILE to the old PC (USB stick is
fine) and run it there:

    pip install pywin32
    python spike_print_test.py

No other project files or packages are needed. The script generates its own
tiny test PDF, cleans up temp files after itself.

What it tests, in order (answers the README's highest-priority open item —
can a PDF be printed from Python on this exact PC and printer, and by which
method?):

  Test 1 — Python can see the installed printers (win32print).
  Test 2 — A RAW plain-text job physically prints via the Windows spooler.
           NOTE: many modern drivers silently ignore RAW text. "Nothing came
           out" here is informative, not fatal — it does NOT mean printing
           is broken.
  Test 3 — A PDF prints via Windows' "print" verb (os.startfile / ShellExecute).
           Depends on a registered PDF handler (Adobe Reader / Edge / etc.).
           Prints to the DEFAULT printer, so make sure the Epson is default.
  Test 4 — A PDF prints silently via SumatraPDF's command line, if it is
           installed. This is the most reliable method and the recommended
           one to adopt (small, free, designed for silent printing).

At the end you get a summary. Record which tests passed — that decision goes
into README Section 5, and app/printer/ will be built around the winning
method. If both PDF tests fail, the documented fallback is converting the
PDF to an image first and printing that (needs extra libraries; we only
build it if we have to).
"""

import os
import shutil
import sys
import tempfile

LINE = "=" * 64


def banner(text: str) -> None:
    print("\n" + LINE)
    print(text)
    print(LINE)


# ---------------------------------------------------------------------------
# Test 1 — enumerate printers
# ---------------------------------------------------------------------------

def list_printers():
    """Return (sorted_printer_names, default_printer_name_or_None)."""
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = [p[2] for p in win32print.EnumPrinters(flags)]
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = None
    return sorted(names), default


# ---------------------------------------------------------------------------
# Test 2 — RAW text job through the spooler
# ---------------------------------------------------------------------------

def print_raw_text(printer_name: str) -> None:
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        # "RAW" datatype: bytes go to the printer/driver unmodified.
        win32print.StartDocPrinter(handle, 1, ("spike-text-test", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(
                handle,
                b"spike_print_test: raw text job via Windows spooler\r\n\f",
            )
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


# ---------------------------------------------------------------------------
# Test 3 — PDF via Windows "print" verb
# ---------------------------------------------------------------------------

def print_pdf_shell_verb(pdf_path: str) -> None:
    """Uses the file association's 'print' verb. Prints to the DEFAULT printer."""
    os.startfile(pdf_path, "print")  # == ShellExecute(verb="print")


# ---------------------------------------------------------------------------
# Test 4 — PDF via SumatraPDF command line (silent)
# ---------------------------------------------------------------------------

SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
]


def find_sumatra():
    found = shutil.which("SumatraPDF")
    if found:
        return found
    for path in SUMATRA_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def print_pdf_sumatra(sumatra_exe: str, pdf_path: str, printer_name: str) -> None:
    import subprocess

    # -print-to names the printer explicitly; -silent suppresses Sumatra's UI.
    result = subprocess.run(
        [sumatra_exe, "-print-to", printer_name, "-silent", pdf_path],
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SumatraPDF exited with code {result.returncode}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )


# ---------------------------------------------------------------------------
# Minimal valid one-page test PDF, generated from scratch (no dependencies)
# ---------------------------------------------------------------------------

def make_test_pdf(path: str) -> None:
    content = (
        b"BT /F1 24 Tf 72 720 Td "
        b"(Printer spike test - if you read this, it worked!) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode()
        + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_position = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()

    with open(path, "wb") as f:
        f.write(bytes(out))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    results = []  # (test_name, "PASS"/"FAIL"/"SKIP", detail)

    banner("PRINTER SPIKE TEST — run this ON the PC the printer is plugged into")

    try:
        import win32print  # noqa: F401  (pywin32 presence check)
    except ImportError:
        print(
            "pywin32 is not installed here. Run:\n"
            "    pip install pywin32\n"
            "and try again."
        )
        return 1

    # -- Test 1: printer visibility -----------------------------------------
    printer_name = None
    try:
        printers, default = list_printers()
        print(f"\nPrinters Windows reports ({len(printers)}):")
        for name in printers:
            marker = "  (default)" if name == default else ""
            print(f"  - {name}{marker}")
        if not printers:
            raise RuntimeError("No printers found — is the Epson installed on this PC?")
        if default and default in printers:
            printer_name = default
        else:
            printer_name = printers[0]
        results.append(("T1 list printers", "PASS", f"target: {printer_name}"))
    except Exception as exc:
        results.append(("T1 list printers", "FAIL", str(exc)))

    print(
        f"\n>>> Everything below prints to: {printer_name}\n"
        ">>> Keep paper loaded and watch the physical printer."
    )
    input("\nPress Enter when ready...")

    temp_dir = tempfile.mkdtemp(prefix="spike_print_")
    pdf_path = os.path.join(temp_dir, "spike_test.pdf")
    try:
        make_test_pdf(pdf_path)
        print(f"Test PDF generated: {pdf_path}")

        # -- Test 2: RAW text -------------------------------------------------
        try:
            print_raw_text(printer_name)
            results.append((
                "T2 RAW text job",
                "PASS",
                "job accepted by spooler; check if paper came out "
                "(drivers often ignore RAW text — not fatal)",
            ))
        except Exception as exc:
            results.append(("T2 RAW text job", "FAIL", str(exc)))

        # -- Test 3: ShellExecute print verb ----------------------------------
        try:
            print("Submitting PDF via 'print' verb...")
            print_pdf_shell_verb(pdf_path)
            results.append((
                "T3 PDF via print verb",
                "PASS",
                "handed to Windows' PDF handler; check paper. "
                "NOTE: depends on an installed PDF reader being the handler",
            ))
        except Exception as exc:
            results.append(("T3 PDF via print verb", "FAIL", str(exc)))

        # -- Test 4: SumatraPDF -----------------------------------------------
        sumatra = find_sumatra()
        if sumatra:
            try:
                print(f"Printing via SumatraPDF: {sumatra}")
                print_pdf_sumatra(sumatra, pdf_path, printer_name)
                results.append((
                    "T4 PDF via SumatraPDF",
                    "PASS",
                    f"sumatra at {sumatra}; check paper (recommended method)",
                ))
            except Exception as exc:
                results.append(("T4 PDF via SumatraPDF", "FAIL", str(exc)))
        else:
            results.append((
                "T4 PDF via SumatraPDF",
                "SKIP",
                "SumatraPDF not found. Install it (free, tiny) from "
                "https://www.sumatrapdfreader.org and re-run if T3 failed",
            ))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    banner("SUMMARY")
    for name, status, detail in results:
        print(f"[{status:4}] {name}: {detail}")

    passed = [r for r in results if r[1] == "PASS"]
    print(
        "\nWhat to do with this result:\n"
        "  - T4 PASS  -> best outcome: app/printer/ will use SumatraPDF.\n"
        "  - T3 only  -> usable, but fragile (depends on the default PDF app);\n"
        "                still install SumatraPDF if you can.\n"
        "  - T2 only  -> spooler works but PDF needs a renderer: we go with\n"
        "                the PDF->image fallback (extra libraries, tell me).\n"
        "  - All FAIL -> note the error messages; we debug driver/queue first\n"
        "                (README Section 14 'printer driver problems' row).\n"
        "\nRecord this summary — it decides the app/printer/ design.\n"
    )
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())

