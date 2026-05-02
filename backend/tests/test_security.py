from unittest.mock import patch

from security import create_auth_token, hash_password, verify_auth_token, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("secret-123")
    assert hashed.startswith("pbkdf2$")
    assert verify_password("secret-123", hashed)
    assert not verify_password("wrong", hashed)


def test_non_pbkdf2_hash_is_rejected():
    # Non-pbkdf2$ values (plaintext, empty, bcrypt, etc.) must always be rejected.
    assert not verify_password("legacy", "legacy")
    assert not verify_password("admin", "admin@123")
    assert not verify_password("anything", "")
    assert not verify_password("x", "$2b$12$somethingthatmightlooklikebcrypt")


def test_auth_token_roundtrip():
    token = create_auth_token(7, "recruiter")
    payload = verify_auth_token(token)
    assert payload is not None
    assert payload["user_id"] == 7
    assert payload["role"] == "recruiter"


def test_expired_token_is_rejected():
    # Freeze token creation at epoch 0; real clock is vastly past the TTL.
    with patch("security.time") as mock_time:
        mock_time.time.return_value = 0
        token = create_auth_token(1, "applicant")
    assert verify_auth_token(token) is None


def test_malformed_tokens_are_rejected():
    assert verify_auth_token("") is None
    assert verify_auth_token("nodothere") is None
    assert verify_auth_token("garbage.garbage") is None
    assert verify_auth_token("!!invalid!!.base64") is None
    assert verify_auth_token(".") is None


def test_tampered_signature_is_rejected():
    token = create_auth_token(1, "applicant")
    payload_b64, sig_b64 = token.split(".", 1)
    bad_sig = sig_b64[:-1] + ("A" if sig_b64[-1] != "A" else "B")
    assert verify_auth_token(f"{payload_b64}.{bad_sig}") is None


def test_tampered_payload_is_rejected():
    import base64
    token = create_auth_token(1, "applicant")
    _, sig_b64 = token.split(".", 1)
    # Swap in a payload claiming admin role — signature check must catch it.
    bad_payload = base64.urlsafe_b64encode(b"1:admin:9999999999").rstrip(b"=").decode()
    assert verify_auth_token(f"{bad_payload}.{sig_b64}") is None

