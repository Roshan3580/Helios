#!/usr/bin/env python3
"""Mint an additional E2E JWT using the PEM written by jwks_server.py."""

from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization

KID = "helios_e2e_kid_1"
DEFAULT_CLIENT_ID = "client_e2e_helios"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pem-file", type=Path, required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--sub", default="user_01E2EUSER000000000000002")
    parser.add_argument("--sid", default="session_01E2ESESSION00000000002")
    parser.add_argument("--token-out", type=Path, required=True)
    parser.add_argument("--expires-in", type=int, default=3600)
    args = parser.parse_args()

    private_key = serialization.load_pem_private_key(
        args.pem_file.read_bytes(), password=None
    )
    now = int(time.time())
    claims = {
        "iss": args.issuer,
        "exp": now + args.expires_in,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "sub": args.sub,
        "sid": args.sid,
        "org_id": args.org_id,
        "client_id": args.client_id,
        "role": "member",
    }
    token = pyjwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": KID}
    )
    args.token_out.write_text(token, encoding="utf-8")
    args.token_out.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
