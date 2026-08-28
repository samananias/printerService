"""
Windows printing code (Phase 7: detection; Phase 5: submission).

Importing win32print at module level would crash the whole service on any
machine without pywin32 (e.g. a non-Windows dev box), so the import happens
inside the functions. The service stays bootable everywhere; only printing
endpoints report a problem — exactly like SOURCE_OF_TRUTH Section 4 wants.

🔴 (Section 5) Job SUBMISSION method is undecided until the old-PC spike
(spike_print_test.py) runs. This module currently covers only listing.
"""

from app.models.printing import PrinterInfo


def list_printers() -> list[PrinterInfo]:
    """Ask Windows which printers exist and which is the default."""
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = sorted(p[2] for p in win32print.EnumPrinters(flags))
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = None
    return [PrinterInfo(name=name, is_default=(name == default)) for name in names]
