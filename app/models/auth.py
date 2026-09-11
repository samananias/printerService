"""Pydantic shapes for the PIN login gate (docs/LOGIN_PLAN.md §4)."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Body of POST /auth/login — the only place the raw PIN is submitted."""

    pin: str


class LoginResponse(BaseModel):
    """200 body of POST /auth/login — the opaque token the client stores
    (never the PIN) and sends in X-Session-Token from then on."""

    token: str


class AuthStatus(BaseModel):
    """GET /auth/status — checked before the page renders anything.

    session_valid is None when no token was sent (or no PIN is
    configured, making the whole gate moot), False when a token was sent
    but isn't currently active (wrong, or the server restarted since it
    was issued), True when good."""

    pin_required: bool
    session_valid: bool | None = None
