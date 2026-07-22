"""Password hashing and session signing — stdlib only (secrets/hashlib/hmac),
per the api/ import allowlist. No external auth library, no network."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

SESSION_TTL_HOURS = 12
_SECRET_FILE = Path(__file__).resolve().parent.parent / ".session_secret"


def _load_or_create_secret() -> bytes:
    """Server-side signing secret, generated once and kept out of git
    (.session_secret is gitignored).

    KNOWN LIMITATION (accepted for the single-tester tool, noted in
    FRONTEND_IMPLEMENTATION_PLAN.md F5 follow-ons): there is no rotation
    path — regenerating or losing this file invalidates every active
    session (users just log in again; no data is affected)."""
    if _SECRET_FILE.exists():
        return bytes.fromhex(_SECRET_FILE.read_text(encoding="utf-8").strip())
    secret = secrets.token_bytes(32)
    _SECRET_FILE.write_text(secret.hex(), encoding="utf-8")
    return secret


SECRET = _load_or_create_secret()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def _sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_session(user_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    expires = int((now + timedelta(hours=SESSION_TTL_HOURS)).timestamp())
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def parse_session(token: str, now: datetime | None = None) -> int | None:
    """user_id if the token is authentic and unexpired, else None."""
    now = now or datetime.now(UTC)
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(payload), parts[2]):
        return None
    try:
        user_id, expires = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if now.timestamp() > expires:
        return None
    return user_id
