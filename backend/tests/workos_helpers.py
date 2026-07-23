"""Deterministic WorkOS-shaped JWT/JWKS fixtures for backend tests.

Generates a local RSA key pair and a JWKS document; no WorkOS network access
occurs anywhere in the test suite.
"""

from __future__ import annotations

import json
import time
import uuid

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_CLIENT_ID = "client_test_helios"
# Official WorkOS AuthKit access-token issuer (the API root, no path). The
# application is identified by the separate ``client_id`` claim, not the issuer.
TEST_ISSUER = "https://api.workos.com"
TEST_KID = "sso_oidc_key_test_1"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_JWK = json.loads(
    pyjwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key())
)
_PUBLIC_JWK.update({"kid": TEST_KID, "alg": "RS256", "use": "sig"})

JWKS_DOCUMENT = {"keys": [_PUBLIC_JWK]}

# A second key for rotation tests.
_ROTATED_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ROTATED_KID = "sso_oidc_key_test_2"
_ROTATED_JWK = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(_ROTATED_KEY.public_key()))
_ROTATED_JWK.update({"kid": ROTATED_KID, "alg": "RS256", "use": "sig"})
JWKS_DOCUMENT_ROTATED = {"keys": [_PUBLIC_JWK, _ROTATED_JWK]}

# An unrelated key whose signatures must never verify.
_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

DEFAULT_SUB = "user_01TESTUSER0000000000000001"
DEFAULT_SID = "session_01TESTSESSION000000000001"
DEFAULT_ORG = "org_01TESTORG0000000000000001"


def make_token(
    *,
    sub: str | None = DEFAULT_SUB,
    sid: str | None = DEFAULT_SID,
    org_id: str | None = DEFAULT_ORG,
    client_id: str | None = TEST_CLIENT_ID,
    issuer: str = TEST_ISSUER,
    kid: str = TEST_KID,
    algorithm: str = "RS256",
    expires_in: int = 300,
    role: str | None = "member",
    permissions: list[str] | None = None,
    key=None,
    extra_claims: dict | None = None,
) -> str:
    now = int(time.time())
    claims: dict = {
        "iss": issuer,
        "exp": now + expires_in,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    if sub is not None:
        claims["sub"] = sub
    if sid is not None:
        claims["sid"] = sid
    if org_id is not None:
        claims["org_id"] = org_id
    if client_id is not None:
        claims["client_id"] = client_id
    if role is not None:
        claims["role"] = role
    if permissions is not None:
        claims["permissions"] = permissions
    if extra_claims:
        claims.update(extra_claims)

    signing_key = key if key is not None else _PRIVATE_KEY
    if algorithm.startswith("HS"):
        signing_key = "hs-test-secret-0123456789abcdef0123456789abcdef"
    return pyjwt.encode(claims, signing_key, algorithm=algorithm, headers={"kid": kid})


def make_token_with_rotated_key(**kwargs) -> str:
    return make_token(kid=ROTATED_KID, key=_ROTATED_KEY, **kwargs)


def make_token_with_wrong_key(**kwargs) -> str:
    return make_token(key=_WRONG_KEY, **kwargs)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
