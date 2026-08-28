"""GET /printers — what Windows can see (Phase 7, SOURCE_OF_TRUTH Section 11)."""

from fastapi import APIRouter, HTTPException

from app.models.printing import PrinterInfo
from app.printer.windows import list_printers

router = APIRouter()


@router.get("/printers", response_model=list[PrinterInfo])
def printers():
    """List printers Windows knows about, default flagged.

    Confirms the driver/detection half of the pipeline. Test #4 in Section 13
    ("Can Python correctly list the Epson L3210?") is exactly this endpoint
    run on the old PC.
    """
    try:
        return list_printers()
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="pywin32 is not available — printer listing needs Windows.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not list printers: {exc}"
        )
