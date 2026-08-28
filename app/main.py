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
  P2  <- we are here: GET /health
  P4: POST /print upload endpoint (wired via app/api/)
  P5: upload handler calls app/printer/ to submit real print jobs
"""

from fastapi import FastAPI

app = FastAPI(
    title="Printer Service",
    description="Android → Wi-Fi → this service → Windows print queue → Epson L3210",
    version="0.1.0",
)


@app.get("/")
def root():
    """Tiny landing page so a browser visit to http://<ip>:8000 shows something."""
    return {
        "service": "printer-service",
        "status": "running",
        "hint": "open /health to check reachability, /docs for interactive API docs",
    }


@app.get("/health")
def health():
    """First thing to check when anything seems broken (SOURCE_OF_TRUTH Section 11).

    Deliberately touches NO printing logic: it answers "is the service up and
    reachable?", nothing more.
    """
    return {"status": "ok"}

