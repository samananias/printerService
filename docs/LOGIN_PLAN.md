# PIN Login Gate — Feasibility, Decision Record & Roadmap

Status: **implemented on branch `auth-security` (2026-09-04).** All §11 open
items are decided; §0's compatibility review ran against the real source.
Decisions are recorded inline — the 🔵/🟡/🔴 tags below are kept for
history, but everything needed to read this as-built is marked ✅.
Goal: since the router's admin panel doesn't give you enough control to
firewall the LAN or spin up an isolated guest network, move the "who's
allowed to use this" boundary up into the app itself — a proper login gate
in front of the existing PIN, instead of relying on network isolation you
can't fully configure.

Claims are tagged like SOURCE_OF_TRUTH / MULTI_FORMAT_PLAN / SCAN_PLAN:
🟢 CONFIRMED FACT · 🔵 RECOMMENDED (decided here) · 🟡 ALTERNATIVE ·
🔴 NEEDS VERIFICATION (read the real code first) · ⚪ FUTURE

---

## 0. Compatibility review — DONE (2026-09-04) 🟢

Ran against the real source, as SCAN_PLAN §0 did. All three assumptions
held; one additional finding (the inline PIN field) is folded into §6/§11.

1. ✅ **Header mechanism confirmed.** `app/services/auth.py` defines
   `require_pin(x_api_pin: Header)` — a FastAPI dependency reading the
   **`X-API-PIN`** header, compared to `API_PIN` with
   `hmac.compare_digest`, raising 401 otherwise. Attached via
   `Depends(require_pin)` to exactly the state-changing routes:
   `POST /print`, `DELETE /jobs/{id}`, `POST /jobs/{id}/retry`,
   `POST /scan`, `DELETE /scan/jobs/{id}`. Read-only GETs stay open.
2. ✅ **Client-side confirmed — and worse than assumed.** Both pages in
   `app/api/web.py` render a `type="password"` field (`id="pin"`) and the
   JS reads it fresh at *every* action (~6 sites), sending `X-API-PIN`
   only when non-empty. Nothing is persisted. With the gate in place this
   inline field is redundant, so the decision (§11) is to **remove it**
   and route every client request through the stored session token.
3. ✅ **Config is load-once, no hot reload.** `app/config.py` parses
   `.env` once at module import; `API_PIN` is bound at import time and
   `auth.py` imports it by value. A PIN change *is* a restart — the
   §3.2/"key insight" design is correct as written.

Also checked: no test pins the old `id="pin"` HTML field (only the
`X-API-PIN` header in API tests, which this feature does not touch), and
the suite stood at **316 tests** when this plan was written (not the 342
cited from SCAN_PLAN §8).

---

## 1. Executive summary — the 5 answers

| # | Question | Decision |
|---|----------|----------|
| 1 | Show the gate when no PIN is configured? | **No.** Fully invisible — no overlay, no extra requests — when `PIN` is unset/empty. |
| 2 | How do we avoid re-entering the PIN every time ("save password")? | Store an **opaque session token** client-side (not the raw PIN), issued once at login. |
| 3 | Why does it reappear if the PIN changes? | It doesn't need special-casing — see #4. Since config only loads at startup, a PIN change already requires a restart. |
| 4 | Why does it reappear if "the server is down"? | Sessions live **only in server memory**. A process restart empties that memory, so every previously issued token silently stops working — the client discovers this on its next check-in and re-prompts. |
| 5 | Does this touch the existing print/scan request flow? | **No.** Existing API requests keep sending the raw PIN header exactly as they do today; the token is a separate, additive "is my remembered credential still good" check — same non-regression guarantee SCAN_PLAN gave the print pipeline. *(As built, the browser itself switched from the per-action PIN field to the stored token — §11's "inline PIN field removed" decision — but `X-API-PIN` is accepted unchanged for direct API use.)* |

**Key insight:** #3 and #4 are the same mechanism. You asked for two
separate re-prompt triggers ("PIN changed" and "server down"), but because
this codebase already loads config once at startup (no hot reload), a PIN
change *is* a restart. One rule — "sessions don't survive a process
restart" — satisfies both requirements without extra bookkeeping, extra
config, or a database. This is the same kind of trade-off SOURCE_OF_TRUTH
§12 already made peace with for jobs ("in-memory... accepted trade-off")
and it's arguably a *feature* here, not a limitation: it means a session
can never quietly outlive the PIN that authorized it.

---

## 2. Why an app-level gate instead of network isolation 🔵

SOURCE_OF_TRUTH §8 always treated the shared PIN as "cheap insurance," on
the assumption that the real boundary was the LAN itself (private-profile
firewall, no port forwarding, §7/§8). With no ability to firewall
device-to-device or run a genuinely isolated guest network on this router,
that assumption weakens — anything else on the Wi-Fi can currently reach
the service and try the PIN on every request. This plan doesn't change the
threat model (still LAN-only, still "sensible defaults, not enterprise
hardening," §8) — it just gives the PIN a real front door instead of
letting each POST silently 401 with no clear "you need to sign in" moment,
and adds a small amount of session hygiene (§3, §7) that's easy to get for
free while doing that.

---

## 3. Session design — the core mechanism 🔵

### 3.1 What gets added

New file `app/services/sessions.py`, structured like the other in-memory
stores in this codebase (job dict + lock, scan store's own connection +
`RLock`):

```python
# app/services/sessions.py  (sketch — confirm naming against auth.py in Phase 0)
import secrets
import threading

_lock = threading.RLock()
_active_tokens: set[str] = set()          # cleared for free on process restart

def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _active_tokens.add(token)
    return token

def is_valid(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        return token in _active_tokens
```

No persistence, no SQLite table, no TTL bookkeeping — deliberately. The
process's memory lifetime *is* the session lifetime, which is exactly the
property §1's answer #4 needs.

### 3.2 How it plugs into the existing PIN check ✅ (decided: separate header)

`app/services/auth.py`'s `require_pin` currently checks "does the request's
`X-API-PIN` header match `API_PIN`." Extend it — additively — to also
accept a currently-valid session token sent in a **separate
`X-Session-Token` header**:

```
require_pin passes IF
    API_PIN is unset                            (unchanged, auth disabled)
    OR X-API-PIN equals API_PIN                 (unchanged, today's check)
    OR X-Session-Token is an active session     (new)
```

Every existing test that exercises "PIN header equals PIN" keeps passing
unmodified — this is a pure addition to what counts as valid, not a
replacement.

### 3.4 Where the token lives — DECIDED: separate `X-Session-Token` header ✅

The plan originally leaned toward dual-accepting "PIN or token" in the
same header, but reading the real code settled it the other way:

- 🔵 **Chosen: separate `X-Session-Token` header.** The real
  `require_pin` is tiny and its 401 message ("Send it in the 'X-API-PIN'
  header") stays literally true. Dual-accept would make every
  state-changing route's auth decision depend on session state and make
  that error message ambiguous, to save one header — bad trade.
- 🟡 ~~Same header, dual-accept~~ — rejected for the reasons above.

### 3.3 What the client actually stores

- **The raw PIN is only ever sent once**, in the login request. It is
  never written to `localStorage`/`sessionStorage`.
- After a successful login, the client stores the **token** (not the PIN)
  under a namespaced key, e.g. `printerService.pinToken`.
- "Remember this device" (checked by default) decides *where*:
  checked → `localStorage` (survives closing the browser); unchecked →
  `sessionStorage` (cleared when the tab/browser session ends). Same
  token, same server-side validity rule either way — this checkbox is
  purely a client-side storage choice, no server involvement.

---

## 4. API design 🔵

Two new endpoints, same conventions as `/scanners` and `/print`
(SCAN_PLAN §4, SOURCE_OF_TRUTH §11) — status codes and shape match what's
already established in this codebase rather than inventing new ones.

| Endpoint | Method | Request | Response | Why |
|---|---|---|---|---|
| `/auth/status` | GET | optional: stored token, sent the same way any authed request sends it | `{"pin_required": true/false, "session_valid": true/false/null}` | **The endpoint the page calls before rendering anything.** Never requires the PIN itself — mirrors `/scanners`' "must be checkable before you know whether to show UI for it" role. `session_valid` is `null` when no token was sent, `false` when a token was sent but isn't currently active (wrong, or server restarted since it was issued), `true` when good. Always open, always 200 — same "never errors" spirit as `/scanners`. |
| `/auth/login` | POST | `{"pin": "..."}` | **200** `{"token": "..."}` on match; **401** with a clear message on mismatch | The only place the raw PIN is ever submitted after this feature ships. Deliberately open (can't require the PIN to submit the PIN) but see §7 for lightweight abuse protection. |

No `/auth/logout` in v1 — see §9 Phase 4 for the optional "forget this
device" button.

---

## 5. Client-side flow 🔵

1. Either page (`/` or `/scan`) loads. Before rendering the rest of the
   page's interactive bits, it reads any stored token and calls
   `GET /auth/status` (attaching the token the same way other requests
   attach credentials).
2. `pin_required: false` → nothing else happens. No overlay is ever built
   or shown, no further auth-related requests are made for the rest of
   the session. This satisfies your "only shows when a PIN is configured"
   requirement literally — the gate doesn't exist on a no-PIN install.
3. `pin_required: true, session_valid: true` → the stored token still
   works. Overlay stays hidden; the rest of the page behaves exactly as
   it does today.
4. `pin_required: true, session_valid: false or null` → show the overlay
   (§6). The user enters the PIN once, `POST /auth/login`, on success the
   returned token is stored per the Remember checkbox (§3.3), overlay
   hides, page proceeds normally.
5. **Reappearing automatically without a manual refresh:** the existing
   health/connectivity poll (WEBDESIGN_PLAN §4's `wifi-high`/`wifi-slash`
   indicator, and the jobs list's 5s refresh per WEBDESIGN_PLAN §11)
   already round-trips to the server periodically. Piggyback the same
   `session_valid` check onto that existing poll (or a lightweight
   parallel one) so that if the server process restarts while the page is
   left open, the very next poll notices `session_valid: false` and
   raises the overlay again — the user doesn't have to manually reload
   the tab to discover they've been logged out.
6. Wrong PIN → `/auth/login` 401 → inline error in the overlay
   (`--red-pen`, system font, per WEBDESIGN_PLAN §3's rule that error
   detail is never handwriting), stored token (if any stale one existed)
   is discarded, focus stays in the field.

---

## 6. UI / visual design — a Revision-3 addendum to WEBDESIGN_PLAN.md 🔵

This needs its own small addendum to WEBDESIGN_PLAN.md rather than a
free-standing style, because the notebook world (§0–§2 of that doc) has
firm opinions this has to honor: no cards/boxes, ruled-paper-is-the-
container, handwriting only for short labels, `--red-pen` reserved for
real errors, self-hosted assets only, mobile-first.

**Proposed treatment:** rather than inventing a floating modal/card (which
WEBDESIGN_PLAN's "no cards, shadows, or boxed containers" rule explicitly
forbids), treat the gate as **a third page of the same notebook** — a
full-viewport takeover using the identical ruled/margin `.page` background
(§2's recipe), so it never reads as a foreign dialog bolted onto the app:

```
┌──┬──────────────────────────┐
│  │ printerService     [wifi] │  ← same header zone, nav box hidden
├──┼──────────────────────────┤     while locked (nothing to nav to yet)
│▍ │ [lock-key] Enter PIN      │  ← handwriting heading, sits on the
│▍ │                           │     first rule like any other heading
│▍ │ [__________________]     │  ← type="password", --paper-raised field
│▍ │ ☐ Remember this device   │  ← handwriting label (short → allowed)
│▍ │                           │
│▍ │      [ Unlock ]           │  ← the existing drawn-box button style,
│▍ │                           │     --ink-blue border, handwriting label
│▍ │ Incorrect PIN.            │  ← only on error: system font, --red-pen
└──┴──────────────────────────┘
```

- Icon: reuse `lock-key`, already in the WEBDESIGN_PLAN §4 mapping for
  PIN — no new icon needed for v1.
- No show/hide-password eye toggle in v1 🔵 — it's one more icon and one
  more piece of state for a form that's used rarely once "remember" is
  on; skip it and keep the field a plain `type="password"`. Note as a
  🟡 later addition if it turns out to be annoying in practice.
- `autocomplete="current-password"` on the field so the *browser's own*
  password manager can also offer to remember it — free, complementary
  to the app-level token, and no extra code.
- `aria-modal="true"`, labelled, autofocus on the field, focus trapped
  while shown, since this genuinely blocks use of the page (unlike every
  other overlay/drawer in WEBDESIGN_PLAN, which are conveniences, not
  gates).
- New pinned hooks to add (and keep, per WEBDESIGN_PLAN §0's "test-pinned
  hooks survive" rule): `id="pinOverlay"`, `id="pinInput"`,
  `id="pinRemember"`, `id="pinError"`, `onclick="submitLogin()"` — naming
  in the same style as the existing `startScan()`/`scanBtn` pattern.
- Shared between both pages: since `/` and `/scan` each build their HTML
  independently (WEBDESIGN_PLAN §11's "assemble from the same CSS/JS
  parts"), factor the overlay markup + JS into one function both page
  builders call, the same way the nav-box hand-off is shared.

---

## 7. Security 🔵

Same posture as SOURCE_OF_TRUTH §8 / SCAN_PLAN §7 — sensible home-lab
defaults, not enterprise hardening:

- Still LAN-only, still no internet exposure, still plain HTTP — the
  token travels over the same unencrypted local connection the PIN
  already does today, so this is not a new exposure, just a narrower one
  (the raw PIN itself now crosses the wire once per device instead of on
  every single request).
- Token generated with `secrets.token_urlsafe(32)` (256 bits) — not
  guessable; comparison against `settings.PIN` uses a constant-time
  comparison (`hmac.compare_digest`), same as any credential check.
- 🔵 **Recommended, not blocking:** a small in-memory failed-attempt
  counter per source IP on `/auth/login` (e.g., a short delay or lockout
  after 5 wrong PINs in a minute). This is easy to add now that there's a
  single dedicated login surface, and meaningfully raises the cost of
  someone on the LAN brute-forcing the PIN — something that was true of
  the *old* per-request check too, just less visible as a single target.
  Not required for a working v1; fine to land in Phase 4.
- Server-generated tokens only, never client-chosen — same
  path-traversal-style discipline SOURCE_OF_TRUTH §9 already applies to
  filenames.
- No new attack surface beyond what §16/§8 already accept: still nothing
  beyond SQLite (and this doesn't even need SQLite — sessions are memory-
  only), still no OAuth/accounts, still PIN/LAN as the whole model.

---

## 8. Edge cases 🔵

- **No PIN configured at all:** `/auth/status` always returns
  `pin_required: false`; no overlay code path is ever reached. Setting a
  PIN later (and restarting) turns the gate on for every device on the
  next load — nothing to migrate.
- **Token present but server restarted since issuance:** `session_valid:
  false`; overlay reappears; one PIN entry issues a fresh token; nothing
  else on the device needs re-entering (no re-upload, no lost job state —
  jobs live in SQLite already, per SOURCE_OF_TRUTH §12, untouched by this
  feature).
- **Two devices, same PIN:** independent tokens, independent sessions;
  restarting the server logs both out simultaneously (both discover it on
  their next poll) — consistent, no partial-logout state to reason about.
- **"Remember" unchecked, tab closed and reopened:** `sessionStorage` is
  gone → overlay shows again, exactly like a fresh device. Working as
  intended — that's what unchecking the box means.
- **PIN typed wrong repeatedly:** 401 each time, inline error, no lockout
  in v1 unless you take the §7 recommendation into Phase 1 early.
- **Existing print/scan requests during the transition:** unaffected in
  every case — §3.2's change is additive, so a device that never visits
  the login gate at all (e.g., an old bookmark hitting `/print` directly)
  still authenticates exactly as it does today, with the raw PIN header.

---

## 9. Phased roadmap 🔵 → all phases built ✅ (2026-09-04)

- **Phase 0 — compatibility review (§0):** ✅ done — results recorded at
  §0; all three assumptions confirmed, the inline-PIN-field finding
  folded into §11.
- **Phase 1 — backend session support:** ✅ done —
  `app/services/sessions.py` (module-level set + `RLock`, `create_session`/
  `is_valid`/`reset`), the additive `X-Session-Token` branch in
  `require_pin`, `app/models/auth.py` (`LoginRequest`, `LoginResponse`,
  `AuthStatus`), `app/api/auth.py` (`GET /auth/status`, `POST /auth/login`),
  router mounted in `main.py`, and an autouse `fresh_sessions` conftest
  fixture (the session set is module-level state, so tests reset it the
  same way the job store gets a fresh one). One deviation from the §4
  table: `/auth/login` returns **400** (not silently 200) when no PIN is
  configured — there is nothing to log in to.
- **Phase 2 — login gate UI:** ✅ done — `GATE_HTML` shared by both pages
  in `app/api/web.py`, wired to `/auth/status` + `/auth/login`, Remember
  checkbox driving `localStorage` vs `sessionStorage`, inline error via
  `.status.err`, old inline `id="pin"` field and its ~6 JS read sites
  removed in favor of one `authHeaders()` helper.
- **Phase 3 — auto re-prompt on restart:** ✅ done — `checkGate()` runs
  at load and on the health poll's 30 s cadence; a `session_valid`
  flip to false raises the overlay without a manual reload. A 401 from
  any protected route also re-raises the gate mid-action.
- **Phase 4 (⚪ optional / v2):** login-attempt throttling (§7); a
  "forget this device" button; a soft max-age on tokens; a show/hide
  password toggle. Not built.

---

## 10. Testing plan 🔵

Mirrors the existing suite's core trick (SOURCE_OF_TRUTH §13): fake the
boundary, never rely on real timing or a real browser.

| What | How |
|---|---|
| Session store: create/validate, "restart" clears everything | Unit tests against a fresh module import / re-instantiated set |
| PIN-check dependency: old PIN-header path unaffected; new token path accepted when valid, rejected when stale/unknown | Unit tests, same fake-module style already used for `win32print`/`win32com` |
| `/auth/status`: never errors; correct `pin_required`/`session_valid` combinations, including "no token sent" (`null`) | API tests via `TestClient` |
| `/auth/login`: correct PIN → 200 + usable token; wrong PIN → 401; missing field → 422 | API tests |
| Web page: overlay hooks present; overlay absent entirely when `pin_required:false`; Remember checkbox picks `localStorage` vs `sessionStorage`; error text never uses the handwriting face | Web-page tests, same style as `TestNotebookRedesign` |
| **Regression guard:** the full existing suite (316 tests when this plan was written) still passes unmodified | Just run it |

Same CI gates apply: `ruff check .` + `pytest --cov-fail-under=90`.

---

## 11. Open items for you to decide before Phase 1

- [x] §3.4 — **separate `X-Session-Token` header** (decided against the
      plan's original lean, after reading the real `auth.py` — see §3.4).
- [x] §7 — **throttling deferred to Phase 4** (not required for the
      feature to work correctly, and Phase 1 is already the riskiest
      phase).
- [x] §6 — **full-page takeover confirmed** — the "third page of the
      notebook" treatment, leaning into "no cards, ever."
- [x] Remember-this-device default: **checked by default** (least
      friction; matches a personal home-lab device).
- [x] *(New item, raised by the §0 review)* The old inline
      `id="pin"` field on both pages is **removed** — with the gate and
      the stored token, retyping the PIN per page load is exactly the
      friction this feature exists to remove. All ~6 JS header-building
      sites switch to a shared `authHeaders()` that sends
      `X-Session-Token`; a 401 mid-action re-raises the gate.
- [x] *(New item, recorded explicitly)* Read-only GETs (`/jobs`,
      `/printers`, `/scanners`, scan downloads) **stay open without any
      credential**, per the existing auth convention. The gate stops
      people from *acting*, not from *reading* — an accepted property of
      the LAN threat model (§2), not an oversight.

---

*Companion to MULTI_FORMAT_PLAN.md, SCAN_PLAN.md, and WEBDESIGN_PLAN.md —
same tagging convention, same "decision record before code" discipline.
No hardware spike required; this is a pure software/UX feature.*

**As-built (2026-09-04):** suite 378 tests, 95.75 % coverage (gate 90 %),
ruff clean — the pre-existing suite passed unmodified throughout; every
test added here is new coverage. WEBDESIGN_PLAN §12 records the visual
addendum; SOURCE_OF_TRUTH §8/§11 record the security and API decisions.