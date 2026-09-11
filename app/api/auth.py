"""Auth endpoints for the PIN login gate (docs/LOGIN_PLAN.md §4).

Two endpoints, same conventions as /scanners and /print:

- GET /auth/status — the endpoint the page calls before rendering
  anything. Never requires the PIN itself and never errors (always 200),
  mirroring /scanners' "must be checkable before you know whether to show
  UI for it" role.
- POST /auth/login — the only place the raw PIN is ever submitted.
  Deliberately open (you can't require the PIN to submit the PIN); abuse
  throttling is a Phase 4 add-on per LOGIN_PLAN §7/§11.
"""

import hmac

from fastapi import APIRouter, Header, HTTPException

from app.config import API_PIN
from app.models.auth import AuthStatus, LoginRequest, LoginResponse
from app.services import sessions

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
def auth_status(
    x_session_token: str | None = Header(default=None),
) -> AuthStatus:
    """Report whether the gate exists and whether a presented token is
    still good. session_valid is None when no token was sent or when no
    PIN is configured (sessions can only exist while a PIN does, so the
    field is simply not meaningful then)."""
    pin_required = bool(API_PIN)
    session_valid = None
    if pin_required and x_session_token:
        session_valid = sessions.is_valid(x_session_token)
    return AuthStatus(pin_required=pin_required, session_valid=session_valid)


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    """Exchange the raw PIN for an opaque session token (one per device).

    401 on a wrong PIN with a clear message; 400 when no PIN is
    configured at all, since there is nothing to log in to."""
    if not API_PIN:
        raise HTTPException(
            status_code=400,
            detail="No PIN is configured — the login gate is disabled.",
        )
    if not request.pin or not hmac.compare_digest(request.pin, API_PIN):
        raise HTTPException(status_code=401, detail="Incorrect PIN.")
    return LoginResponse(token=sessions.create_session())
