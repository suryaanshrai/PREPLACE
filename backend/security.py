import base64
import hashlib
import hmac
import os
import secrets
import time


TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "preplace-dev-secret-change-me")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if not stored.startswith("pbkdf2$"):
        return stored == password

    try:
        _, salt, expected_hex = stored.split("$", 2)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
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
