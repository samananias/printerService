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
