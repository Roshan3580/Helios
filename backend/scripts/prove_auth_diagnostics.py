#!/usr/bin/env python3
"""Checkpoint 28 runtime proof: safe auth diagnostics under the real Uvicorn CLI.

Runs the backend exactly as Render does —
``uvicorn app.main:app --host 127.0.0.1 --port <p> --workers 1`` with no
``--log-config`` and no ``--log-level`` — against a **loopback synthetic JWKS
server** and synthetic RSA-signed tokens. Nothing contacts WorkOS.

It drives the five rejection shapes, captures the server's stdout+stderr, and
asserts that each safe line appears AND that no token, claim value, identifier,
Client ID, header, or cookie reached the stream.

Usage (from backend/):
    .venv/bin/python scripts/prove_auth_diagnostics.py
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

# ---------------------------------------------------------------------------
# Synthetic credentials. Deliberately distinctive so a leak is unmistakable.
# ---------------------------------------------------------------------------
CLIENT_ID = "client_SYNTHETICPROOF0001"
OTHER_CLIENT_ID = "client_SYNTHETICOTHER0002"
ISSUER = "https://api.workos.com"
KID = "sso_oidc_key_SYNTHETICPROOF"
SUB = "user_01SYNTHETICPROOFUSER0001"
SID = "session_01SYNTHETICPROOFSESS001"
ORG = "org_01SYNTHETICPROOFORG00001"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": KID, "alg": "RS256", "use": "sig"})
JWKS = {"keys": [_JWK]}
_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def mint(*, client_id=CLIENT_ID, issuer=ISSUER, expires_in=300, org_id=ORG, key=None) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "exp": now + expires_in,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "sub": SUB,
        "sid": SID,
        "client_id": client_id,
    }
    if org_id:
        claims["org_id"] = org_id
    return pyjwt.encode(claims, key or _KEY, algorithm="RS256", headers={"kid": KID})


class _JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


def main() -> int:
    jwks_port = free_port()
    api_port = free_port()

    jwks_server = HTTPServer(("127.0.0.1", jwks_port), _JwksHandler)
    threading.Thread(target=jwks_server.serve_forever, daemon=True).start()

    env = os.environ.copy()
    env.update(
        {
            # Local environment: this proof is about logging, not the staging
            # deployment contract (covered by its own tests).
            "HELIOS_ENVIRONMENT": "local",
            "HELIOS_DEMO_MODE": "false",
            "HELIOS_E2E_TEST_MODE": "false",
            "HELIOS_ANALYST_NARRATIVE_ENABLED": "false",
            "WORKOS_CLIENT_ID": CLIENT_ID,
            "WORKOS_ISSUER": ISSUER,
            "WORKOS_JWKS_URL": f"http://127.0.0.1:{jwks_port}/jwks",
            "DATABASE_URL": env.get(
                "HELIOS_TEST_DATABASE_URL",
                "postgresql://helios_test:helios_test@localhost:5434/helios_test",
            ),
            "PYTHONUNBUFFERED": "1",
        }
    )

    # EXACTLY the Render start command form: no --log-config, no --log-level.
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

    def drain():
        assert proc.stdout is not None
        for line in proc.stdout:
            captured.append(line.rstrip("\n"))

    threading.Thread(target=drain, daemon=True).start()

    base = f"http://127.0.0.1:{api_port}"
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

        expired = mint(expires_in=-60)
        bad_sig = mint(key=_WRONG_KEY)
        wrong_iss = mint(issuer="https://attacker.example.com")
        wrong_cid = mint(client_id=OTHER_CLIENT_ID)
        no_org = mint(org_id=None)
        all_tokens = [expired, bad_sig, wrong_iss, wrong_cid, no_org]

        cases = [
            ("missing token", "/v2/user/me", None, "auth_missing_token", 401),
            ("expired token", "/v2/user/me", expired, "auth_expired_token", 401),
            ("invalid signature", "/v2/user/me", bad_sig, "auth_invalid_signature", 401),
            ("wrong issuer", "/v2/user/me", wrong_iss, "auth_invalid_issuer", 401),
            ("wrong client id", "/v2/user/me", wrong_cid, "auth_invalid_client_id", 401),
            ("missing org", "/v2/user/projects", no_org, "auth_missing_org", 403),
        ]

        # PHASE 1 — production-shaped traffic: credential in the Authorization
        # header only, exactly as the Helios browser client sends it. The whole
        # captured stream is leak-scanned for this phase.
        results = []
        for name, path, token, expect_reason, expect_status in cases:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            resp = httpx.get(f"{base}{path}", headers=headers, timeout=10.0)
            results.append((name, path, resp.status_code, expect_reason, expect_status))

        time.sleep(1.0)  # let the server flush its stream
        phase1_output = "\n".join(captured)
        phase1_count = len([ln for ln in captured if "human auth rejected:" in ln])

        # PHASE 2 — adversarial query string, to prove the Helios diagnostic line
        # carries the route path ONLY. Note that uvicorn's own access logger
        # echoes the full request line (standard for every web server), so this
        # phase is scanned against the Helios-emitted lines, not the whole
        # stream. Helios's client never puts a credential in a query string.
        qs_marker = "eyJQUERYSTRINGCANARY.aaa.bbb"
        httpx.get(f"{base}/v2/user/me?debug_token={qs_marker}", timeout=10.0)
        time.sleep(1.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        jwks_server.shutdown()

    diagnostics = [ln for ln in captured if "human auth rejected:" in ln]
    helios_lines = "\n".join(
        ln
        for ln in captured
        if "human auth rejected:" in ln or "human auth verifier configured:" in ln
    )

    print("=" * 72)
    print("CAPTURED DIAGNOSTIC LINES (verbatim from the uvicorn process)")
    print("=" * 72)
    for line in diagnostics:
        print(line)
    print()

    failures: list[str] = []

    # 1. Every case produced its expected safe reason + status + path.
    for name, path, got_status, expect_reason, expect_status in results:
        if got_status != expect_status:
            failures.append(f"{name}: HTTP {got_status} != expected {expect_status}")
        expected = f"human auth rejected: reason={expect_reason} status={expect_status} path={path}"
        if not any(line.endswith(expected) for line in diagnostics):
            failures.append(f"{name}: missing line {expected!r}")

    # 2. Exactly one diagnostic per request (phase 1 + the single phase 2 call).
    if phase1_count != len(results):
        failures.append(f"phase 1: expected {len(results)} diagnostics, got {phase1_count}")
    if len(diagnostics) != len(results) + 1:
        failures.append(f"expected {len(results) + 1} diagnostics total, got {len(diagnostics)}")

    # 3. PHASE 1 (production-shaped traffic): nothing sensitive anywhere in the
    #    ENTIRE captured stream — uvicorn access lines included.
    forbidden = {
        "synthetic token": all_tokens,
        "client id": [CLIENT_ID, OTHER_CLIENT_ID],
        "subject": [SUB],
        "session id": [SID],
        "organization id": [ORG],
        "jwt segment marker": ["eyJ"],
        "authorization header": ["Bearer ", "Authorization"],
        "cookie": ["Cookie", "wos-session"],
        "jwks url": [f"127.0.0.1:{jwks_port}", "/jwks"],
        "database url": ["postgresql://", "helios_test"],
        "issuer url": ["api.workos.com", "attacker.example.com"],
    }
    for category, values in forbidden.items():
        for value in values:
            if value and value in phase1_output:
                failures.append(f"LEAK[{category}]: phase-1 stream contains {value[:24]!r}")

    for token in all_tokens:
        for segment in token.split("."):
            if len(segment) > 16 and segment in phase1_output:
                failures.append("LEAK[token segment]: partial token in phase-1 stream")

    # 4. PHASE 2: the Helios diagnostic line must carry the route path only.
    #    Scoped to Helios-emitted lines: uvicorn's access logger echoes the full
    #    request line by design, which this checkpoint does not change.
    for value in (qs_marker, "debug_token", "?", "&"):
        if value in helios_lines:
            failures.append(f"LEAK[query string]: Helios line contains {value!r}")

    # 5. The diagnostic lines must match the exact contract shape.
    shape = re.compile(
        r"human auth rejected: reason=auth_[a-z_]+ status=(401|403) path=/v2/user/[a-z]+$"
    )
    for line in diagnostics:
        if not shape.search(line):
            failures.append(f"line does not match contract shape: {line!r}")

    print("=" * 72)
    if failures:
        print("RESULT: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: PASS")
    print(f"  {len(diagnostics)} safe diagnostic lines, one per rejection")
    print("  phase 1 (credential in Authorization header, as the real client sends it):")
    print("    no token, claim, identifier, client id, header, cookie, JWKS URL,")
    print("    issuer URL, or database URL anywhere in the captured stream")
    print("  phase 2 (adversarial query string): Helios lines carry path= only")
    print()
    print("  NOTE: uvicorn's own access logger echoes the full request line,")
    print("  including any query string, as every web server does. Helios never")
    print("  places a credential in a query string; this checkpoint does not")
    print("  alter uvicorn's access log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
