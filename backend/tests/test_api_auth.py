"""Tests for API authentication and authorisation enforcement.

Uses a minimal FastAPI test-app backed by the real ``security`` module so no
database connection is required.  Each test verifies a different combination of
role / token state against endpoints that share the same guard pattern used in
the actual routers.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from security import create_auth_token, get_current_user


# ── role-guard helpers (mirrors the pattern in each router) ──────────────────

def _require_applicant(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "applicant":
        raise HTTPException(status_code=403, detail="Applicant access required")
    return user


def _require_recruiter(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "recruiter":
        raise HTTPException(status_code=403, detail="Recruiter access required")
    return user


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── minimal test FastAPI app ─────────────────────────────────────────────────

_app = FastAPI()


@_app.post("/applicant-only")
def applicant_ep(user: dict = Depends(_require_applicant)):
    return {"user_id": user["user_id"], "role": user["role"]}


@_app.post("/recruiter-only")
def recruiter_ep(user: dict = Depends(_require_recruiter)):
    return {"user_id": user["user_id"]}


@_app.get("/admin-only")
def admin_ep(user: dict = Depends(_require_admin)):
    return {"user_id": user["user_id"]}


@_app.get("/any-authenticated")
def any_ep(user: dict = Depends(get_current_user)):
    return {"user_id": user["user_id"], "role": user["role"]}


client = TestClient(_app, raise_server_exceptions=False)


# ── helpers ──────────────────────────────────────────────────────────────────

def bearer(role: str, user_id: int = 42) -> dict:
    return {"Authorization": f"Bearer {create_auth_token(user_id, role)}"}


# ── missing / malformed token → 401 ─────────────────────────────────────────

def test_no_token_applicant_endpoint_returns_401():
    assert client.post("/applicant-only").status_code == 401


def test_no_token_recruiter_endpoint_returns_401():
    assert client.post("/recruiter-only").status_code == 401


def test_no_token_admin_endpoint_returns_401():
    assert client.get("/admin-only").status_code == 401


def test_no_token_any_endpoint_returns_401():
    assert client.get("/any-authenticated").status_code == 401


@pytest.mark.parametrize("auth_header", [
    "Basic dXNlcjpwYXNz",            # wrong scheme
    "Bearer",                         # scheme only, no token
    "notbearer sometoken",            # not Bearer
    "",                               # empty
])
def test_malformed_authorization_header_returns_401(auth_header):
    resp = client.get("/admin-only", headers={"Authorization": auth_header})
    assert resp.status_code == 401


# ── wrong role → 403 ─────────────────────────────────────────────────────────

def test_recruiter_cannot_access_applicant_endpoint():
    assert client.post("/applicant-only", headers=bearer("recruiter")).status_code == 403


def test_admin_cannot_access_applicant_endpoint():
    assert client.post("/applicant-only", headers=bearer("admin")).status_code == 403


def test_applicant_cannot_access_admin_endpoint():
    assert client.get("/admin-only", headers=bearer("applicant")).status_code == 403


def test_recruiter_cannot_access_admin_endpoint():
    assert client.get("/admin-only", headers=bearer("recruiter")).status_code == 403


def test_applicant_cannot_access_recruiter_endpoint():
    assert client.post("/recruiter-only", headers=bearer("applicant")).status_code == 403


# ── correct role → 200 ───────────────────────────────────────────────────────

def test_applicant_accesses_applicant_endpoint():
    resp = client.post("/applicant-only", headers=bearer("applicant", user_id=7))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 7
    assert resp.json()["role"] == "applicant"


def test_recruiter_accesses_recruiter_endpoint():
    resp = client.post("/recruiter-only", headers=bearer("recruiter", user_id=5))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 5


def test_admin_accesses_admin_endpoint():
    resp = client.get("/admin-only", headers=bearer("admin", user_id=1))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 1


def test_any_role_accesses_any_authenticated_endpoint():
    for role in ("applicant", "recruiter", "admin"):
        assert client.get("/any-authenticated", headers=bearer(role)).status_code == 200


# ── expired token → 401 ──────────────────────────────────────────────────────

def test_expired_token_returns_401():
    # Freeze time at epoch 0 during token creation so the expiry (86400) has
    # already passed by many years relative to the real current time.
    with patch("security.time") as mock_time:
        mock_time.time.return_value = 0
        old_token = create_auth_token(1, "admin")
    resp = client.get("/admin-only", headers={"Authorization": f"Bearer {old_token}"})
    assert resp.status_code == 401


# ── tampered token → 401 ─────────────────────────────────────────────────────

def test_tampered_payload_returns_401():
    """Swapping in an admin payload with an applicant's signature must fail HMAC."""
    import base64
    applicant_token = create_auth_token(1, "applicant")
    _, sig_b64 = applicant_token.split(".", 1)
    bad_payload = base64.urlsafe_b64encode(b"1:admin:9999999999").rstrip(b"=").decode()
    resp = client.get("/admin-only", headers={"Authorization": f"Bearer {bad_payload}.{sig_b64}"})
    assert resp.status_code == 401


def test_tampered_signature_returns_401():
    token = create_auth_token(1, "applicant")
    payload_b64, sig_b64 = token.split(".", 1)
    bad_sig = sig_b64[:-1] + ("A" if sig_b64[-1] != "A" else "B")
    resp = client.post("/applicant-only", headers={"Authorization": f"Bearer {payload_b64}.{bad_sig}"})
    assert resp.status_code == 401
