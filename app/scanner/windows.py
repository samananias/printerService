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
from contextlib import contextmanager
from pathlib import Path

from app.config import ENABLE_SCAN
from app.models.scanning import DEFAULT_DPI, ScanDevice

logger = logging.getLogger(__name__)

# WIA DeviceInfo.Type values (SCAN_PLAN §2): 1 = scanner, 2 = camera, 3 = video.
WIA_SCANNER_TYPE = 1


@contextmanager
def _com_apartment():
    """COM apartments are per-THREAD: every thread that touches WIA must
    call CoInitialize first, or COM raises CO_E_NOTINITIALIZED
    (-2147221008 — caught live by the Phase 2 smile-check).

    The scan endpoints run on uvicorn's thread-pool threads and the scan
    pipeline on its own background thread — neither is the main thread,
    where importing pywin32 happened to initialize COM. The spike never
    saw this because it called WIA from the main thread.

    Balanced Initialize/Uninitialize around the WIA work. On machines
    without pywin32 (the CI runner) there is no COM at all — yield
    unchanged, so the faked detection/scan tests behave identically.
    """
    try:
        import pythoncom
    except ImportError:
        yield
        return
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def list_scan_devices() -> list[ScanDevice]:
    """Ask Windows which scanners exist right now. NEVER raises.

    COM apartments are per-thread AND a COM proxy must not outlive its
    thread's apartment — _detect_scanners_via_com() does the whole session
    and returns plain data, so its frame (and every COM local) is
    destroyed BEFORE the _com_apartment() block exits and uninitializes
    the thread. Both mistakes were caught live in the Phase 2
    smile-check: skipping CoInitialize gave CO_E_NOTINITIALIZED, and
    letting proxies outlive CoUninitialize segfaulted.
    """
    try:
        with _com_apartment():
            return _detect_scanners_via_com()
    except Exception as exc:
        # Missing pywin32, WIA service disabled, COM blow-up: all mean the
        # same thing to this feature — "no scanner on this machine".
        logger.warning("WIA scanner detection unavailable: %s", exc)
        return []


def _detect_scanners_via_com() -> list[ScanDevice]:
    """The WIA enumeration session (call inside _com_apartment)."""
    import win32com.client

    devices: list[ScanDevice] = []
    manager = win32com.client.Dispatch("WIA.DeviceManager")
    infos = manager.DeviceInfos
    count = infos.Count
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


def scan_flatbed(
    dest: Path, dpi: int = DEFAULT_DPI, color_mode: str = "color"
) -> Path:
    """Transfer one flatbed page to a PNG at `dest` (SCAN_PLAN §5 step 3).

    `dpi`/`color_mode` are the Phase 4 options, applied best-effort by the
    WIA driver — a driver that refuses a value keeps its default (the
    spike's 200-dpi request behaved exactly this way). The PNG lands ONLY
    if the transfer succeeded: WIA's SaveFile refuses to overwrite (spike
    S4's 0x80070050 lesson), so the caller must pass a fresh
    server-generated name — which every caller here does.

    May raise RuntimeError with a phone-readable message (the scan
    pipeline records it as the job's error); the _com_apartment wrapper
    keeps every COM proxy inside the session, so nothing outlives the
    thread's CoUninitialize (see list_scan_devices).
    """
    try:
        with _com_apartment():
            _transfer_flatbed_via_com(dest, dpi, color_mode)
    except RuntimeError:
        raise  # already human-readable ("scanner was not found", ...)
    except Exception as exc:
        raise RuntimeError(_human_scan_error(exc)) from exc
    return dest


def _apply_scan_options(item, dpi: int, color_mode: str) -> None:
    """Request resolution/color on a WIA item, best-effort (never raises).

    Resolution uses the standard "Horizontal/Vertical Resolution"
    properties. Color uses WIA's "Current Intent" (WIA_IPS_CUR_INTENT,
    with WIA_INTENT_IMAGE_TYPE_COLOR=1 / _GRAYSCALE=2), falling back to
    "Bits Per Pixel" (24=RGB / 8=greyscale) for drivers that prefer it.
    """
    _set_item_option(item, "Horizontal Resolution", dpi)
    _set_item_option(item, "Vertical Resolution", dpi)
    intent = WIA_CUR_INTENT_BY_MODE.get(color_mode, WIA_INTENT_COLOR)
    if not _set_item_option(
        item, "Current Intent", intent, prop_id=WIA_IPS_CUR_INTENT
    ):
        _set_item_option(
            item, "Bits Per Pixel", WIA_BITS_BY_MODE.get(color_mode, 24)
        )


def _set_item_option(item, prop_name: str, value, prop_id=None) -> bool:
    """Best-effort set of one WIA item property; never raises. Returns
    whether the driver accepted the set (by name, then by numeric id)."""
    for key in (prop_name, prop_id):
        if key is None:
            continue
        try:
            item.Properties(key).Value = value
            return True
        except Exception:
            continue
    return False


# WIA item option constants (Phase 4).
WIA_IPS_CUR_INTENT = 6146  # WIA_IPS_CUR_INTENT — the color-intent property
WIA_INTENT_COLOR = 1  # WIA_INTENT_IMAGE_TYPE_COLOR
WIA_INTENT_GRAYSCALE = 2  # WIA_INTENT_IMAGE_TYPE_GRAYSCALE
WIA_CUR_INTENT_BY_MODE = {
    "color": WIA_INTENT_COLOR,
    "greyscale": WIA_INTENT_GRAYSCALE,
}
WIA_BITS_BY_MODE = {"color": 24, "greyscale": 8}


def _transfer_flatbed_via_com(dest: Path, dpi: int, color_mode: str) -> None:
    """One flatbed WIA transfer session (call inside _com_apartment)."""
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
        item = items.Item(order[0])
        _apply_scan_options(item, dpi, color_mode)
        image = item.Transfer(WIA_FORMAT_PNG)
        image.SaveFile(str(dest))
        return
    raise RuntimeError(
        "The scanner was not found — check the USB connection and try again."
    )
