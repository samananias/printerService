"""
In-memory session tokens for the PIN login gate (docs/LOGIN_PLAN.md §3).

Design: after a successful POST /auth/login the client holds an opaque
token (secrets.token_urlsafe(32) — 256 bits, server-generated, never
client-chosen) and sends it in the "X-Session-Token" header. The token set
lives ONLY in process memory, structured like this codebase's other
in-memory stores (module-level state + a lock):

- No persistence, no TTL bookkeeping — deliberately. The process's memory
  lifetime IS the session lifetime, which is the property LOGIN_PLAN §1's
  answer #4 needs: a server restart silently invalidates every issued
  token, so a session can never outlive the PIN that authorized it (and
  since config loads once at startup, a PIN change is a restart — one rule
  covers both re-prompt triggers).
- Tokens accumulate only on successful logins, so on a home-lab scale the
  set stays trivially small; no expiry sweep is worth the bookkeeping.
"""

import secrets
import threading

_lock = threading.RLock()
_active_tokens: set[str] = set()


def create_session() -> str:
    """Mint a fresh opaque token and remember it until the process ends."""
    token = secrets.token_urlsafe(32)
    with _lock:
        _active_tokens.add(token)
    return token


def is_valid(token: str | None) -> bool:
    """True only for a token this process issued and has not been
    restarted since. Empty/None is simply invalid, never an error."""
    if not token:
        return False
    with _lock:
        return token in _active_tokens


def reset() -> None:
    """Drop every token — the tests' 'server restart' simulation (the real
    thing happens for free when the process exits)."""
    with _lock:
        _active_tokens.clear()
