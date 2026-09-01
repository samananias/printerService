"""Windows scanner detection via WIA (docs/SCAN_PLAN.md Phase 1).

Shaped like app/printer/windows.py and using its central trick:
win32com.client is imported INSIDE the functions, never at module level.
That keeps the whole app bootable on machines without pywin32 (the Ubuntu
CI runner) and lets tests inject a fake module into sys.modules — the
exact pattern conftest.py's fake_win32print already established.

The hard rule (SCAN_PLAN §3): detection NEVER raises. Every failure —
pywin32 missing, the WIA service disabled, a COM error, one broken device
entry — is logged and reported as "no scanners". The scan feature must be
invisible where it can't work, and must never be the reason the app breaks.

WIA facts the code relies on (proven by spike_scan.py on the real L3210,
S1 plugged AND unplugged):
  - win32com.client.Dispatch("WIA.DeviceManager") gives the device manager;
  - .DeviceInfos is a 1-BASED collection with .Count and .Item(i);
  - an entry is a scanner when its .Type == 1;
  - the friendly name lives in .Properties("Name").Value, not on an
    attribute, so it is read defensively too.
"""

import logging
from pathlib import Path

from app.config import ENABLE_SCAN
from app.models.scanning import ScanDevice

logger = logging.getLogger(__name__)

# WIA DeviceInfo.Type values (SCAN_PLAN §2): 1 = scanner, 2 = camera, 3 = video.
WIA_SCANNER_TYPE = 1


def list_scan_devices() -> list[ScanDevice]:
    """Ask Windows which scanners exist right now. NEVER raises."""
    try:
        import win32com.client

        manager = win32com.client.Dispatch("WIA.DeviceManager")
        infos = manager.DeviceInfos
        count = infos.Count
    except Exception as exc:
        # Missing pywin32, WIA service disabled, COM blow-up: all mean the
        # same thing to this feature — "no scanner on this machine".
        logger.warning("WIA scanner detection unavailable: %s", exc)
        return []

    devices: list[ScanDevice] = []
    for index in range(1, count + 1):  # WIA collections are 1-based
        try:
            info = infos.Item(index)
            if info.Type != WIA_SCANNER_TYPE:
                continue  # a webcam/camera must not pose as a scanner
            devices.append(
                ScanDevice(name=_display_name(info), id=str(info.DeviceID))
            )
        except Exception as exc:
            # One unreadable entry must not hide the healthy scanners.
            logger.warning("skipping unreadable WIA device %d: %s", index, exc)
    return devices


def _display_name(info) -> str:
    """The device's friendly name, read defensively (COM property access)."""
    try:
        return str(info.Properties("Name").Value)
    except Exception:
        return ""


def scan_available() -> bool:
    """True when Windows reports at least one scanner right now.

    Re-probed on every call (no cache): unplugging the USB cable is
    reflected immediately, the same way /printers reflects live win32print
    state (SCAN_PLAN §3.2 step 4). Enumeration is COM-only and cheap.
    """
    return bool(list_scan_devices())


def scanning_supported() -> bool:
    """The two gates ANDed (SCAN_PLAN §3.4): the ENABLE_SCAN kill switch
    AND a scanner actually present. This is the single question the
    /scanners endpoint (and later /scan) answers.

    ENABLE_SCAN is imported by value from app.config — per conftest rule 2,
    tests patch it HERE on this module, not on app.config.
    """
    return ENABLE_SCAN and scan_available()


# ---------------------------------------------------------------------------
# The scan half (SCAN_PLAN §5): one flatbed page out — or a readable error.
#
# Unlike the detection functions above, these MAY raise: RuntimeError with
# a phone-user-readable message, exactly like submit_pdf's contract with
# the print pipeline. The scan pipeline records it as the job's error.
# ---------------------------------------------------------------------------

# WIA's PNG format ID, passed as a raw GUID (SCAN_PLAN §0: avoid
# win32com.client.constants — it needs a makepy-generated module).
WIA_FORMAT_PNG = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"

# WIA error HRESULTs (mapped from the low 32 bits) → what the phone user
# can actually do. Unmapped codes fall back to the raw error text. Same
# spirit as the print engine's SumatraPDF exit-code catalog (p15).
WIA_ERROR_MESSAGES = {
    0x80210001: "The scanner reported a paper jam. Clear it and try again.",
    0x80210002: (
        "No document was detected on the scanner glass. Place the page "
        "face down and try again."
    ),
    0x80210004: (
        "The scanner is offline — check that the printer is powered on and "
        "the USB cable is seated."
    ),
    0x80210005: "The scanner is busy. Wait for the current job and try again.",
    0x80210007: (
        "The scanner needs attention — check that the cover is closed and "
        "look at the error light."
    ),
    0x80210009: (
        "The scanner stopped responding. Re-seat the USB cable and try again."
    ),
    0x8021000C: (
        "The scanner is locked by another application. Close it and try again."
    ),
}


def _human_scan_error(exc: Exception) -> str:
    """Translate a WIA COM error into something a phone user can act on.

    pywin32's com_error buries the HRESULT in args[2][5]; WIA's specific
    codes live in 0x802100xx.
    """
    args = getattr(exc, "args", ())
    scode = None
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 6:
        scode = args[2][5]
    if isinstance(scode, int) and scode < 0:
        mapped = WIA_ERROR_MESSAGES.get(scode & 0xFFFFFFFF)
        if mapped:
            return mapped
    return f"The scan failed: {exc}"


def _item_label(item) -> str:
    """An item's friendly name, trying both WIA property names."""
    for prop in ("Item Name", "Name"):
        try:
            return str(item.Properties(prop).Value)
        except Exception:
            continue
    return ""


def _open_flatbed_item():
    """Connect to the first WIA scanner and return a transferable item.

    Prefers an item whose name mentions "flat" (matters on multi-item
    devices with a feeder); on the L3210 there is exactly one item and it
    IS the flatbed (proven by spike S2).
    """
    import win32com.client

    manager = win32com.client.Dispatch("WIA.DeviceManager")
    infos = manager.DeviceInfos
    for index in range(1, infos.Count + 1):
        info = infos.Item(index)
        if info.Type != WIA_SCANNER_TYPE:
            continue
        device = info.Connect()
        items = device.Items
        order = sorted(
            range(1, items.Count + 1),
            key=lambda i: "flat" not in _item_label(items.Item(i)).lower(),
        )
        return items.Item(order[0])
    raise RuntimeError(
        "The scanner was not found — check the USB connection and try again."
    )


def scan_flatbed(dest: Path) -> Path:
    """Transfer one flatbed page to a PNG at `dest` (SCAN_PLAN §5 step 3).

    Driver-default resolution and color — the user-facing options (dpi,
    color_mode, format) arrive in Phase 4. The PNG lands ONLY if the
    transfer succeeded: WIA's SaveFile refuses to overwrite (spike S4's
    0x80070050 lesson), so the caller must pass a fresh server-generated
    name — which every caller here does.
    """
    try:

        item = _open_flatbed_item()
        image = item.Transfer(WIA_FORMAT_PNG)
        image.SaveFile(str(dest))
    except RuntimeError:
        raise  # already human-readable ("scanner was not found", ...)
    except Exception as exc:
        raise RuntimeError(_human_scan_error(exc)) from exc
    return dest
