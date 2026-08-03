# Hosted beta smoke test

Use this runbook to verify the production-capable hosted beta without changing
hosted configuration. The public endpoints are:

- Frontend: `https://helios-staging-tau.vercel.app`
- Backend: `https://helios-0cqu.onrender.com`

Never copy credentials or sensitive identity data into commands, screenshots,
tickets, chat, or logs. This includes bearer tokens, project API keys, Client
IDs, cookies, authorization headers, database URLs, exact JWT claims, and raw
WorkOS session data. Variable names and public endpoint URLs are safe to record.

## Expected safe diagnostics

The backend startup log may report only these safe verifier fields and values:

```text
environment=staging
client_id_present=true
issuer_client_id_present=true
issuer_mode=multi_application
jwks_mode=derived
```

Do not record identifiers, issuer or JWKS URLs, tokens, headers, cookies,
claims, database details, or session data. A rejected authenticated request may
report the documented safe reason code, HTTP status, and route path only.

## Complete journey

1. Confirm in the Render dashboard that the live service commit is the commit
   under test. Record only the commit SHA.
2. Request `https://helios-0cqu.onrender.com/health/ready` and confirm HTTP 200.
   A free-tier cold start can take up to about one minute. Use bounded manual
   retries. A normal cold start is not an authentication failure.
3. Confirm the startup diagnostic reports the safe WorkOS verifier values
   listed above. Stop if the mode differs. Do not copy surrounding log data.
4. Open a new Incognito or private browsing session at
   `https://helios-staging-tau.vercel.app`.
5. Sign in once through the normal hosted flow. Avoid repeated sign-in attempts
   while the backend is waking.
6. In browser developer tools, confirm `/v2/user/me` returns HTTP 200. Inspect
   only the status, method, and route. Do not copy request or response data.
7. Confirm `/v2/user/projects` returns HTTP 200 using the same safe inspection.
8. Confirm the authenticated shell loads the active organization and identity,
   proving local bootstrap completed. Record only pass or fail.
9. Create one clearly named smoke-test project in the product UI.
10. Create one project API key with trace ingestion and read access. Keep the
    key solely in an approved local secret store or injection mechanism.
11. Configure a disposable local Python environment for the checked-out SDK.
    Inject `HELIOS_API_KEY` locally without echoing it, saving it in shell
    history, or placing it in a file. The SDK must read it through
    `os.environ["HELIOS_API_KEY"]`.
12. Run `examples/python_sdk_quickstart/main.py` against
    `https://helios-0cqu.onrender.com` and send exactly one trace. Treat exporter
    errors as authoritative. Treat the neutral local-completion message as an
    instruction to verify arrival, not as proof of delivery.
13. In the hosted UI, confirm the trace appears in the selected project's trace
    list, then open its detail page and span timeline.
14. Run deterministic trace analysis and confirm evidence-backed results render.
15. Open Dashboard and confirm it aggregates the stored smoke-test telemetry.
16. Open Insights, run project analysis, and confirm the result renders for the
    selected project.
17. Revoke the smoke-test project API key in the product UI.
18. Without changing the local injected key, run the same one-trace ingestion
    once more. Do not add retries or fallback credentials.
19. Confirm ingestion returns HTTP 401. Do not copy headers or response bodies.
    The exporter error is authoritative, and the example must not print a
    positive delivery claim.
20. Refresh the selected project's trace list and confirm no new trace was
    stored. The project must still contain exactly the first accepted trace.
21. Unset `HELIOS_API_KEY` and any other local secret environment variables used
    for the check. Close the private browsing session.
22. Record pass or fail for each numbered step, the tested commit SHA, and safe
    HTTP status codes only. Never attach secrets or sensitive identity data.

## Pass criteria

All 22 steps pass, the revoked key is rejected with 401, and the project still
contains exactly the one trace accepted before revocation. A cold-start delay is
acceptable when readiness eventually returns 200 within the bounded manual
retry window.
