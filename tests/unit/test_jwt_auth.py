from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bank_rag.infrastructure.security.jwt_auth import InvalidToken, decode_token

SECRET = "test-secret"
ALGORITHM = "HS256"


def _make_token(**overrides: object) -> str:
    payload = {
        "sub": "customer-123",
        "role": "customer",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        **overrides,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def test_decodes_valid_customer_token():
    claims = decode_token(_make_token(), SECRET, ALGORITHM)
    assert claims.subject == "customer-123"
    assert claims.is_employee is False


def test_decodes_valid_employee_token():
    claims = decode_token(_make_token(role="employee"), SECRET, ALGORITHM)
    assert claims.is_employee is True


def test_rejects_expired_token():
    expired = _make_token(exp=datetime.now(UTC) - timedelta(minutes=1))
    with pytest.raises(InvalidToken):
        decode_token(expired, SECRET, ALGORITHM)


def test_rejects_unexpected_role():
    with pytest.raises(InvalidToken):
        decode_token(_make_token(role="admin"), SECRET, ALGORITHM)


def test_rejects_token_signed_with_wrong_secret():
    forged = _make_token()
    with pytest.raises(InvalidToken):
        decode_token(forged, "a-different-secret", ALGORITHM)


def test_rejects_token_missing_required_claims():
    payload = {"sub": "customer-123"}  # missing role and exp
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    with pytest.raises(InvalidToken):
        decode_token(token, SECRET, ALGORITHM)
