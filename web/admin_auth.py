"""A standalone credential for the admin dashboard.

Deliberately share nothing with the app's user authentication. The dashboard
used to be reachable by signing in with a Google account whose email appeared
in ADMIN_EMAILS, which makes the blast radius of that one Google account the
whole admin surface -- a phished password, a stale session on a shared laptop,
or a Firebase project configured to let anyone sign up all lead to the same
place. Here the only key is a passphrase that exists on the server and nowhere
else, so compromising any user account grants exactly nothing.

Properties this relies on:

- The passphrase is never stored, only a PBKDF2 hash of it (werkzeug's
  default). ADMIN_PASSWORD_HASH holds the hash; the plaintext lives in the
  operator's password manager and nowhere in this repository.
- Comparison goes through `check_password_hash`, which compares digests rather
  than raw strings, so a wrong guess costs the same time as a near-miss.
- Sessions are signed and timestamped with itsdangerous, so a cookie cannot be
  forged without SECRET_KEY and cannot outlive its window even if stolen.
- It fails closed. No hash or no secret key means the dashboard is off, not
  open -- a missing environment variable must never be the thing standing
  between an attacker and the data.
- Attempts are rate limited per IP with a lockout, because a passphrase with
  no attempt limit is a passphrase you can grind.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

COOKIE_NAME = "rosetta_admin"
SESSION_MAX_AGE = 60 * 60 * 4  # four hours, then sign in again

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # fifteen minutes after five wrong guesses

_SALT = "rosetta-admin-session-v1"

_attempts: dict[str, deque[float]] = {}
_lock = threading.Lock()


def password_hash() -> str:
    return os.environ.get("ADMIN_PASSWORD_HASH", "").strip()


def _secret_key() -> str:
    return os.environ.get("SECRET_KEY", "").strip()


def is_configured() -> bool:
    """Both halves must be present. Either one missing disables the dashboard."""
    return bool(password_hash()) and bool(_secret_key())


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret_key(), salt=_SALT)


def locked_out(ip: str) -> int:
    """Seconds remaining on this IP's lockout. 0 when it may try again."""
    now = time.monotonic()
    with _lock:
        seen = _attempts.get(ip)
        if not seen:
            return 0
        while seen and now - seen[0] > LOCKOUT_SECONDS:
            seen.popleft()
        if len(seen) < MAX_ATTEMPTS:
            return 0
        return max(0, int(LOCKOUT_SECONDS - (now - seen[0])) + 1)


def _record_failure(ip: str) -> None:
    now = time.monotonic()
    with _lock:
        seen = _attempts.setdefault(ip, deque())
        while seen and now - seen[0] > LOCKOUT_SECONDS:
            seen.popleft()
        seen.append(now)
        # Don't let the table grow without bound on a long-lived instance.
        if len(_attempts) > 512:
            for stale in [k for k, v in _attempts.items() if not v or now - v[-1] > LOCKOUT_SECONDS]:
                del _attempts[stale]


def clear_attempts(ip: str) -> None:
    with _lock:
        _attempts.pop(ip, None)


def reset_state() -> None:
    """Drop all lockout state. For tests."""
    with _lock:
        _attempts.clear()


def verify_passphrase(passphrase: str, ip: str) -> bool:
    """Check a passphrase, recording the attempt against `ip`."""
    if not is_configured() or not isinstance(passphrase, str) or not passphrase:
        return False
    if check_password_hash(password_hash(), passphrase):
        clear_attempts(ip)
        return True
    _record_failure(ip)
    return False


def issue_session() -> str:
    # A random nonce so two sessions issued in the same second aren't identical
    # tokens, which keeps one leaked cookie from being obviously reusable.
    return _serializer().dumps({"v": 1, "n": secrets.token_urlsafe(8)})


def valid_session(token: str | None) -> bool:
    if not is_configured() or not token:
        return False
    try:
        _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return True


if __name__ == "__main__":  # pragma: no cover
    # Generate a hash to paste into ADMIN_PASSWORD_HASH:
    #     python web/admin_auth.py "your long passphrase"
    import sys

    if len(sys.argv) != 2:
        print('usage: python web/admin_auth.py "your passphrase"')
        raise SystemExit(1)
    print(generate_password_hash(sys.argv[1]))
