"""GET /scanners — what Windows' WIA layer can see (docs/SCAN_PLAN.md §4).

Mirrors app/api/printers.py in shape, with one crucial difference: this
endpoint NEVER errors. available=false + devices=[] is the normal, healthy
answer on a scanner-less setup — the web page uses it to decide whether to
render the Scan section at all (SCAN_PLAN §1 answer 5).

Read-only GET → deliberately no PIN (app/services/auth.py convention:
only state-changing routes are pinned).
"""

from fastapi import APIRouter

from app.models.scanning import ScannersInfo
from app.scanner.windows import ENABLE_SCAN, list_scan_devices

router = APIRouter()


@router.get("/scanners", response_model=ScannersInfo)
def scanners() -> ScannersInfo:
    """List scanners Windows knows about, plus the "offered" flag.

    ENABLE_SCAN (kill switch) AND at least one detected scanner = offered.
    Anything else reports available=false and an empty list — the phone
    simply never shows a Scan option, exactly like today's print-only page.
    """
    devices = list_scan_devices()  # never raises (SCAN_PLAN §3.2)
    if not (ENABLE_SCAN and devices):
        return ScannersInfo(available=False, devices=[])
    return ScannersInfo(available=True, devices=devices)
