"""
Shared-PIN authentication (Phase 8, SOURCE_OF_TRUTH Section 8).

Design: a single fixed PIN the client sends in the "X-API-PIN" header.
- If API_PIN is empty (the default in .env.example), auth is DISABLED —
  fine for a home-lab MVP where everyone on the Wi-Fi is trusted.
- If set, state-changing endpoints (POST /print, DELETE /jobs/{id}) require
  it. Read-only GETs (/health, /jobs, /printers) stay open: seeing status
  leaks nothing dangerous, and it keeps the phone UI's polling simple.

This is deliberately NOT user accounts/OAuth (Section 16) — it's the cheap,
educational first step into auth concepts: prove you know a shared secret.

Note the constant-time comparison (hmac.compare_digest): comparing secrets
with plain == leaks tiny timing hints about how many characters matched.
Irrelevant for a home PIN, but it costs nothing to do correctly.
"""

import hmac

from fastapi import Header, HTTPException

from app.config import API_PIN


def require_pin(x_api_pin: str | None = Header(default=None)) -> None:
    """FastAPI dependency: attach to any route that changes state."""
    if not API_PIN:
        return  # auth disabled

    if not x_api_pin or not hmac.compare_digest(x_api_pin, API_PIN):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing PIN. Send it in the 'X-API-PIN' header.",
        )
