"""Real JWT verification, replacing the placeholder token decode.

Employee vs customer distinction comes from a `role` claim issued by the
bank's identity provider, never inferred from a naming convention in the
raw token string. HS256 with a shared secret is the minimum viable setup
for a single backend service; if multiple services must verify tokens
independently, swap to RS256 and fetch the IdP's JWKS instead of a shared
secret — the call site (`dependencies.get_identity`) does not need to change.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    is_employee: bool


def decode_token(token: str, secret: str, algorithm: str, audience: str | None = None) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            audience=audience,
            options={"require": ["sub", "role", "exp"]},
        )
    except InvalidTokenError as exc:
        raise InvalidToken(str(exc)) from exc

    role = payload.get("role")
    if role not in ("customer", "employee"):
        raise InvalidToken(f"unexpected role claim: {role!r}")

    return TokenClaims(subject=payload["sub"], is_employee=role == "employee")
