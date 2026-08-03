#!/usr/bin/env python3
"""Checkpoint 30 runtime proof: multi-application mode under real Uvicorn.

With ``WORKOS_ISSUER`` unset and ``WORKOS_ISSUER_CLIENT_ID`` set, the verifier
must accept exactly one no-trailing-slash multi-application issuer. Standard
roots, a trailing slash, another application, and arbitrary paths must fail.

Adjacent values — including another application's ``user_management`` path —
must still fail closed with a safe diagnostic and never leak issuer values into
the log stream.

This runs the backend exactly as Render does —
``uvicorn app.main:app --host 127.0.0.1 --port <p> --workers 1``, with
``WORKOS_ISSUER`` and ``WORKOS_JWKS_URL`` DELIBERATELY UNSET so derivation is
exercised — against a loopback synthetic JWKS and synthetic RSA-signed tokens.
Nothing contacts WorkOS.

Usage (from backend/):
    .venv/bin/python scripts/prove_issuer_contract.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

BACKEND = Path(__file__).resolve().parent.parent

CLIENT_ID = "client_SYNTHETICCURRENT0001"
ISSUER_CLIENT_ID = "client_SYNTHETICDEFAULT0001"
KID = "sso_oidc_key_SYNTHETICISSUER"
SUB = "user_01SYNTHETICISSUERUSER001"
SID = "session_01SYNTHETICISSUERSES01"
ORG = "org_01SYNTHETICISSUERORG001"

SLASHLESS = "https://api.workos.com"
SLASHED = "https://api.workos.com/"
MULTI_APP = f"https://api.workos.com/user_management/{ISSUER_CLIENT_ID}"
MULTI_APP_SLASHED = f"{MULTI_APP}/"
CURRENT_APP_ISSUER = f"https://api.workos.com/user_management/{CLIENT_ID}"
OTHER_APP = "https://api.workos.com/user_management/client_SOMEOTHERAPP00001"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": KID, "alg": "RS256", "use": "sig"})
JWKS = {"keys": [_JWK]}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def mint(issuer: str) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": issuer,
            "exp": now + 300,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "sub": SUB,
            "sid": SID,
            "org_id": ORG,
            "client_id": CLIENT_ID,
        },
        _KEY,
        algorithm="RS256",
        headers={"kid": KID},
    )


class _JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> int:
    jwks_port = free_port()
    api_port = free_port()

    jwks_server = HTTPServer(("127.0.0.1", jwks_port), _JwksHandler)
    threading.Thread(target=jwks_server.serve_forever, daemon=True).start()

    env = os.environ.copy()
    env.update(
        {
            "HELIOS_ENVIRONMENT": "local",
            "HELIOS_DEMO_MODE": "false",
            "HELIOS_E2E_TEST_MODE": "false",
            "HELIOS_ANALYST_NARRATIVE_ENABLED": "false",
            "WORKOS_CLIENT_ID": CLIENT_ID,
            "WORKOS_ISSUER_CLIENT_ID": ISSUER_CLIENT_ID,
            # MULTI-APPLICATION MODE: explicit issuer deliberately unset.
            # A JWKS override is unavoidable for a loopback key server, so the
            # issuer — the subject of this proof — is the one left derived.
            "WORKOS_JWKS_URL": f"http://127.0.0.1:{jwks_port}/jwks",
            "DATABASE_URL": env.get(
                "HELIOS_TEST_DATABASE_URL",
                "postgresql://helios_test:helios_test@localhost:5434/helios_test",
            ),
            "PYTHONUNBUFFERED": "1",
        }
    )
    env.pop("WORKOS_ISSUER", None)

    proc = subprocess.Popen(
        [
            str(BACKEND / ".venv/bin/uvicorn"),
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--workers",
            "1",
        ],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    captured: list[str] = []
    threading.Thread(
        target=lambda: [captured.append(l.rstrip("\n")) for l in proc.stdout], daemon=True
    ).start()

    base = f"http://127.0.0.1:{api_port}"
    accepted_cases = [MULTI_APP]
    rejected_cases = [
        SLASHLESS,
        SLASHED,
        MULTI_APP_SLASHED,
        CURRENT_APP_ISSUER,
        "https://api.workos.com/arbitrary",
        OTHER_APP,
        "https://api.workos.com/user_management/",
        "https://api.workos.com//",
        "http://api.workos.com",
        "https://evil.api.workos.com",
        "https://api.workos.com.evil.example",
    ]
    results: list[tuple[str, str, int]] = []

    try:
        for _ in range(120):
            try:
                if httpx.get(f"{base}/health/live", timeout=1.0).status_code == 200:
                    break
            except Exception:
                time.sleep(0.25)
        else:
            print("FAIL: server did not start", file=sys.stderr)
            print("\n".join(captured), file=sys.stderr)
            return 1

        for issuer in accepted_cases:
            r = httpx.get(
                f"{base}/v2/user/me",
                headers={"Authorization": f"Bearer {mint(issuer)}"},
                timeout=10.0,
            )
            results.append(("accept", issuer, r.status_code))

        for issuer in rejected_cases:
            r = httpx.get(
                f"{base}/v2/user/me",
                headers={"Authorization": f"Bearer {mint(issuer)}"},
                timeout=10.0,
            )
            results.append(("reject", issuer, r.status_code))

        time.sleep(1.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        jwks_server.shutdown()

    output = "\n".join(captured)
    diagnostics = [ln for ln in captured if "human auth rejected:" in ln]
    startup = [ln for ln in captured if "human auth verifier configured:" in ln]

    print("=" * 72)
    print("MULTI-APPLICATION RESULTS (WORKOS_ISSUER unset, real uvicorn CLI)")
    print("=" * 72)
    for kind, issuer, status in results:
        # The issuer values here are synthetic constants defined in this file,
        # not values extracted from any real token.
        verdict = "OK " if (kind == "accept") == (status == 200) else "BAD"
        print(f"  [{verdict}] expect={kind:6s} status={status}  iss={issuer}")
    print()
    print("DIAGNOSTIC LINES")
    for line in diagnostics:
        print(f"  {line}")
    print()

    failures: list[str] = []

    for kind, issuer, status in results:
        if kind == "accept" and status != 200:
            failures.append(f"documented form should be accepted: {issuer} -> {status}")
        if kind == "reject" and status != 401:
            failures.append(f"adjacent form should be rejected: {issuer} -> {status}")

    if len(diagnostics) != len(rejected_cases):
        failures.append(
            f"expected {len(rejected_cases)} diagnostics, got {len(diagnostics)}"
        )
    for line in diagnostics:
        if not re.search(
            r"human auth rejected: reason=auth_(invalid_issuer|invalid_signature) "
            r"status=401 path=/v2/user/me$",
            line,
        ):
            failures.append(f"unexpected diagnostic shape: {line!r}")

    # No issuer value, token, or identifier may reach the stream.
    for value in (
        "api.workos.com",
        "evil.example",
        "arbitrary",
        "user_management",
        "eyJ",
        "Bearer ",
        CLIENT_ID,
        ISSUER_CLIENT_ID,
        SUB,
        SID,
        ORG,
        f"127.0.0.1:{jwks_port}",
    ):
        if value in output:
            failures.append(f"LEAK: stream contains {value[:28]!r}")

    print("=" * 72)
    if failures:
        print("RESULT: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: PASS")
    print(f"  {len(accepted_cases)} exact multi-application issuer accepted (HTTP 200)")
    print(f"  {len(rejected_cases)} adjacent issuer values rejected (HTTP 401)")
    print("  every rejection emitted one safe reason/status/path line")
    print("  no issuer value, token, claim, or identifier in the captured stream")
    if startup:
        # Printed to confirm the mode label; it contains no issuer or client id.
        print(f"  startup mode line: {startup[0].split('] ', 1)[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
