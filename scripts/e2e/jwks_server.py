#!/usr/bin/env python3
"""Ephemeral JWKS + JWT minting for Helios browser E2E (no WorkOS network)."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_ORG = "org_01E2EORG00000000000000001"
DEFAULT_SUB = "user_01E2EUSER000000000000001"
DEFAULT_SID = "session_01E2ESESSION00000000001"
KID = "helios_e2e_kid_1"


class E2EKeys:
    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(
            pyjwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key())
        )
        public_jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}

    def pem_bytes(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def mint(
        self,
        *,
        issuer: str,
        org_id: str = DEFAULT_ORG,
        sub: str = DEFAULT_SUB,
        sid: str = DEFAULT_SID,
        expires_in: int = 3600,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": issuer,
            "exp": now + expires_in,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "sub": sub,
            "sid": sid,
            "org_id": org_id,
            "role": "member",
        }
        return pyjwt.encode(
            claims, self.private_key, algorithm="RS256", headers={"kid": KID}
        )


def serve_jwks(keys: E2EKeys, host: str, port: int) -> ThreadingHTTPServer:
    document = json.dumps(keys.jwks).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") in {"/jwks", "/.well-known/jwks.json"}:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(document)))
                self.end_headers()
                self.wfile.write(document)
                return
            if self.path in {"/health", "/"}:
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--org-id", default=DEFAULT_ORG)
    parser.add_argument("--token-out", type=Path, required=True)
    parser.add_argument("--pem-out", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()

    keys = E2EKeys()
    args.pem_out.write_bytes(keys.pem_bytes())
    args.pem_out.chmod(0o600)
    token = keys.mint(issuer=args.issuer, org_id=args.org_id)
    args.token_out.write_text(token, encoding="utf-8")
    args.token_out.chmod(0o600)
    server = serve_jwks(keys, args.host, args.port)
    args.ready_file.write_text("ready\n", encoding="utf-8")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
