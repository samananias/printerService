"""
Printer Service — application entry point.

Phase status (README Section 9): P0 scaffold only.

Later phases fill this in:
  P2: the FastAPI app instance + GET /health endpoint.
  P4: the /print upload endpoint (wired via app/api/).
  P5: upload handler calls app/printer/ to submit real print jobs.

Run (from the project root, once P2 lands):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
