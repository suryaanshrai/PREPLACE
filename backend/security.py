import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException


TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))

_TOKEN_SECRET_DEFAULT = "preplace-dev-secret-change-me"
_raw_secret = os.getenv("TOKEN_SECRET", _TOKEN_SECRET_DEFAULT)
if _raw_secret == _TOKEN_SECRET_DEFAULT:
    import warnings
    warnings.warn(
        "TOKEN_SECRET is using the insecure default value. "
        "Set the TOKEN_SECRET environment variable to a strong random secret before deploying.",
        stacklevel=2,
    )
TOKEN_SECRET = _raw_secret

# OWASP 2023 recommendation: ≥ 210,000 iterations for PBKDF2-SHA256
_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    # Reject any hash that isn't in our expected pbkdf2$ format rather than
    # falling back to a plaintext comparison (which would be timing-unsafe
    # and allows legacy cleartext passwords to persist indefinitely).
    if not stored.startswith("pbkdf2$"):
        return False

    try:
        _, salt, expected_hex = stored.split("$", 2)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("utf-8"))


def create_auth_token(user_id: int, role: str) -> str:
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}:{role}:{exp}".encode("utf-8")
    sig = hmac.new(TOKEN_SECRET.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def verify_auth_token(token: str):
    if not token or "." not in token:
        return None

    p_b64, s_b64 = token.split(".", 1)
    try:
        payload = _b64d(p_b64)
        sig = _b64d(s_b64)
    except Exception:
        return None

    expected = hmac.new(TOKEN_SECRET.encode("utf-8"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None

    try:
        user_id_str, role, exp_str = payload.decode("utf-8").split(":", 2)
        user_id = int(user_id_str)
        exp = int(exp_str)
    except Exception:
        return None

    if int(time.time()) > exp:
        return None

    return {"user_id": user_id, "role": role, "exp": exp}


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency — extracts and validates the Bearer token.

    Returns a dict with ``user_id`` (int) and ``role`` (str).
    Raises HTTP 401 on missing/invalid/expired tokens.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization scheme; use Bearer <token>")
    payload = verify_auth_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_role(*allowed_roles: str):
    """Return a FastAPI dependency that enforces one of the given roles."""
    def _dep(user: dict = _current_user_dep()) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _dep


def _current_user_dep():
    # Avoid a circular reference when building require_role closures.
    return get_current_user
