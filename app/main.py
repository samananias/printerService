"""
Printer Service — application entry point (Phase 2: Python Server).

Run from the project root:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Concept map (README Section 15):
  uvicorn        = the ENGINE that listens on TCP port 8000 and accepts
                   connections. It knows nothing about printers.
  app (FastAPI)  = decides what to do with each HTTP request ("routing").
  @app.get(...)  = "when a GET request arrives for this path, call this
                   function; whatever dict it returns becomes the JSON body".
  --host 0.0.0.0 = listen on ALL network interfaces so the phone can reach
                   the service. Omitting this makes the server localhost-only
                   — the classic reason a phone "can't connect".
  --port 8000    = which "mailbox" on this PC the server claims. Must match
                   the Windows Firewall rule (allow_firewall_8000.bat).

Phase status (SOURCE_OF_TRUTH Section 9):
  P2: GET /health  ✅ done
  P4: POST /print upload endpoint (app/api/print.py)  ✅ done
  P6: mobile web page (app/api/web.py, GET /)  ✅ done
  P7: /printers, /jobs, /jobs/{id} (GET/DELETE)  ✅ done
  P8: logging, PIN auth, error hardening  ✅ done
  P5: uploads submitted to the Windows print queue via SumatraPDF  ✅ built,
      end-to-end paper test pending SumatraPDF installation
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.api.print import router as print_router
from app.api.printers import router as printers_router
from app.api.web import router as web_router
from app.services.logging_setup import setup_logging
from app.services.uploads import sweep_stale_uploads


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup and once at shutdown.

    Startup: configure logging, then sweep uploads/ of files left behind by
    a previous run — the temp-file hygiene SOURCE_OF_TRUTH Section 8 asks
    for. (Phase 5 also deletes each file right after it's printed; the sweep
    is the safety net for crashes.)
    """
    setup_logging()

    removed = sweep_stale_uploads()
    if removed:
        print(f"[startup] swept {removed} stale upload(s) from a previous run")
    yield
    # Shutdown: nothing to clean yet.


app = FastAPI(
    title="Printer Service",
    description="Android → Wi-Fi → this service → Windows print queue → Epson L3210",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(print_router)


@app.get("/health")
def health():
    """First thing to check when anything seems broken (SOURCE_OF_TRUTH Section 11).

    Deliberately touches NO printing logic: it answers "is the service up and
    reachable?", nothing more.
    """
    return {"status": "ok"}


# GET / serves the mobile web page (Option B): on the phone you open the
# server's address and get a file-picker UI instead of raw JSON.
app.include_router(web_router)
app.include_router(printers_router)
app.include_router(jobs_router)

