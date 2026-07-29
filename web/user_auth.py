"""Server-side verification of the Firebase ID tokens the browser already sends.

The sign-in gate in the page was decoration. Nothing on the server checked it,
so every AI endpoint answered a plain curl from anyone who knew the URL, and
each of those calls spends Groq quota. This closes that.

Why not a shared password: the app already signs everyone in, guests included
(anonymous auth issues a real ID token like any other). Requiring that token
adds no new secret to distribute, no new prompt for the user, and gives each
request a stable `uid` -- which is a far better rate-limit key than an IP that
half the internet shares behind CGNAT.

Why no service account: an ID token is an RS256 JWT signed by Google, and
`verify_firebase_token` validates it against Google's *public* certificates.
It needs the project ID to check the audience and nothing else, so this works
on a deployment that has only the same public config the browser already holds.
Signature, expiry, issuer and audience are all checked; a token minted for
another Firebase project fails on audience.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

# One transport, reused: it caches Google's signing certificates, and building
# a fresh one per request would refetch them on every single call.
_transport = google_requests.Request()
_transport_lock = threading.Lock()

# Verification is a signature check plus a cert fetch. Caching the decoded
# result for the token's own lifetime keeps a burst of calls from repeating it.
_VERIFIED_TTL_SECONDS = 300
_verified: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def project_id() -> str:
    return os.environ.get("FIREBASE_PROJECT_ID", "").strip()


def is_enforceable() -> bool:
    """Whether tokens can be checked at all. Without a project ID they cannot."""
    return bool(project_id())


def reset_state() -> None:
    """Drop cached verifications. For tests."""
    with _cache_lock:
        _verified.clear()


def verify(token: str | None) -> dict[str, Any] | None:
    """Return the token's claims, or None if it is missing, invalid or expired."""
    if not token or not is_enforceable():
        return None

    now = time.monotonic()
    with _cache_lock:
        hit = _verified.get(token)
        if hit and hit[0] > now:
            return hit[1]

    try:
        with _transport_lock:
            claims = google_id_token.verify_firebase_token(
                token, _transport, audience=project_id()
            )
    except Exception:
        # Any failure -- malformed, bad signature, expired, wrong audience --
        # is the same answer to the caller. Distinguishing them would only
        # tell an attacker which part of a forgery to fix.
        return None

    if not isinstance(claims, dict) or not claims.get("sub"):
        return None

    with _cache_lock:
        _verified[token] = (now + _VERIFIED_TTL_SECONDS, claims)
        # Bound the table on a long-lived instance.
        if len(_verified) > 512:
            for stale in [k for k, (expiry, _) in _verified.items() if expiry <= now]:
                _verified.pop(stale, None)
    return claims


def bearer_token(authorization_header: str) -> str | None:
    if not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[7:].strip()
    return token or None
