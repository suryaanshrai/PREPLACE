from security import create_auth_token, hash_password, verify_auth_token, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("secret-123")
    assert hashed.startswith("pbkdf2$")
    assert verify_password("secret-123", hashed)
    assert not verify_password("wrong", hashed)


def test_legacy_plaintext_password_fallback():
    assert verify_password("legacy", "legacy")
    assert not verify_password("other", "legacy")


def test_auth_token_roundtrip():
    token = create_auth_token(7, "recruiter")
    payload = verify_auth_token(token)
    assert payload is not None
    assert payload["user_id"] == 7
    assert payload["role"] == "recruiter"
