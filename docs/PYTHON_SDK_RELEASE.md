# Python SDK release runbook

This runbook covers the first public release of the Helios Observatory Python
SDK. The distribution is `helios-observatory-sdk`, the import package is
`helios_sdk`, and the planned first public version is `0.2.0`.

The repository and SDK are licensed under the Apache License, Version 2.0.
Copyright 2026 Roshan Raj. The package-local `sdk/python/LICENSE` must remain
byte-for-byte identical to the root `LICENSE`.

## Release contract

| Item | Required value |
| --- | --- |
| PyPI project | `helios-observatory-sdk` |
| Import package | `helios_sdk` |
| Version source | `sdk/python/pyproject.toml` |
| Planned version | `0.2.0` |
| Release tag | `python-sdk-v0.2.0` |
| GitHub repository | `Roshan3580/Helios` |
| Publishing workflow | `publish-python-sdk.yml` |
| GitHub environment | `pypi` |
| Authentication | PyPI Trusted Publishing through GitHub OIDC |

The release workflow runs only for a published GitHub Release. It rejects a
tag outside `python-sdk-v<major>.<minor>.<patch>`, rejects a metadata version
mismatch, rejects a version that already exists on PyPI, and requires the
released commit to be merged into the default branch. Only the publication job
has `id-token: write`; that job does not check out or execute repository code.
It downloads the artifacts produced by the unprivileged verification job.

No `PYPI_API_TOKEN`, password, or other long-lived publishing credential is
used or expected.

## Local release validation

Create an isolated development environment, then run the reproducible gate:

```bash
cd sdk/python
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cd ../..
PYTHON_BIN=sdk/python/.venv/bin/python bash scripts/build-python-sdk-release.sh
```

The script removes only the SDK's validated generated build directories. It
then runs `python -m build`, `python -m twine check`, strict wheel and sdist
allowlists, metadata and secret scans, clean installation of the base package,
the `otel` extra, the `openai` extra, combined extras, and a wheel rebuilt from
the sdist. Every installed shape runs `pip check`, public imports, and the
runtime version check. It never uploads a package.

Ordinary CI repeats canonical SDK tests and artifact validation on Python 3.10,
3.11, 3.12, and 3.13. Ordinary CI has read-only repository permission and no
OIDC permission.

## One-time account and publisher setup

Complete these human-controlled steps after the release-foundation pull
request is reviewed and merged:

1. Recheck both direct JSON endpoints and confirm that each returns HTTP 404
   without a redirect:
   - `https://pypi.org/pypi/helios-observatory-sdk/json`
   - `https://test.pypi.org/pypi/helios-observatory-sdk/json`
2. Create or sign in to the intended PyPI account.
3. Enable two-factor authentication for the PyPI account.
4. Create a pending PyPI Trusted Publisher for the first release with these
   exact values:
   - PyPI project: `helios-observatory-sdk`
   - GitHub owner: `Roshan3580`
   - GitHub repository: `Helios`
   - Workflow: `publish-python-sdk.yml`
   - Environment: `pypi`
5. Create the GitHub environment named `pypi`.
6. Add required reviewers to the `pypi` environment where the repository plan
   supports them. Restrict deployment branches or tags to the release policy.
7. Do not create a PyPI API token or GitHub publishing secret.

The repository does not include a TestPyPI publishing workflow. A second
privileged environment and publisher would add first-release ambiguity without
improving the local artifact evidence. The same wheel and sdist are fully
validated before production publication. Add a separate, manually triggered
TestPyPI workflow later only if a distinct `testpypi` environment and Trusted
Publisher are deliberately approved.

## Publish the first release

1. Merge the reviewed release-foundation pull request.
2. Confirm the complete CI suite passes on `main`, including all four Python
   package matrix jobs.
3. Recheck that `helios-observatory-sdk` remains unavailable on PyPI and
   TestPyPI.
4. Confirm `sdk/python/pyproject.toml` still declares version `0.2.0`.
5. Run the local release-validation command from a clean checkout.
6. Create the tag `python-sdk-v0.2.0` at the reviewed `main` commit.
7. Push only that tag. Never force-push or move a published release tag.
8. Create and publish a GitHub Release for `python-sdk-v0.2.0`. A draft release
   does not publish the package.
9. Review the verification job. It must run the canonical tests, build one
   wheel and one sdist, run `twine check`, inspect contents and metadata, test
   installed artifacts, and upload the verified distributions as one GitHub
   Actions artifact.
10. Approve the protected `pypi` environment deployment if required.
11. Confirm the publication job downloads the verified artifact and publishes
    with PyPI Trusted Publishing and attestations.
12. Confirm the workflow reports exactly these files:
    - `helios_observatory_sdk-0.2.0-py3-none-any.whl`
    - `helios_observatory_sdk-0.2.0.tar.gz`
13. Confirm PyPI displays the Apache-2.0 license expression, Python requirement,
    README, repository, issue tracker, documentation, and hosted beta links.

The action keeps `skip-existing` disabled. An already-published filename or
version is an error, not a condition to ignore.

## Post-publication verification

Use a new environment that is outside the repository:

```bash
python3 -m venv /tmp/helios-pypi-verification
/tmp/helios-pypi-verification/bin/python -m pip install \
  "helios-observatory-sdk[otel,openai]==0.2.0"
/tmp/helios-pypi-verification/bin/python -m pip check
/tmp/helios-pypi-verification/bin/python -c \
  'import helios_sdk; from helios_sdk import Helios; print(helios_sdk.__version__)'
```

Then complete the hosted verification:

1. Create a temporary project API key with `traces:ingest` access.
2. Keep the key only in the local process environment. Never paste it into an
   issue, log, release note, or browser bundle.
3. Send one uniquely named real trace to the hosted beta.
4. Confirm the trace appears under the expected project and organization.
5. Revoke the temporary key.
6. Retry ingestion and confirm the revoked key receives HTTP 401.
7. Remove the local environment variable and temporary virtual environment.
8. Record only non-secret evidence such as the package version, trace ID, HTTP
   status, and verification time.

## Rollback reality

PyPI files and versions are immutable release records. Never delete, overwrite,
or reuse a published version number. If `0.2.0` is defective, fix the source and
publish a higher corrected version. Yanking can discourage new installations,
but it is not deletion and does not make the version reusable. A compromised
credential or package requires incident response in addition to a corrected
release.

## Checkpoint 32B: production install-copy update

Checkpoint 32 does not advertise a package that does not exist yet. Run this
checklist immediately after the PyPI release and hosted verification succeed.

The primary production replacement is:

```bash
pip install "helios-observatory-sdk[otel,openai]"
```

Use the smallest sufficient extra for each location:

| Location | Current repository instruction | Checkpoint 32B replacement |
| --- | --- | --- |
| `src/routes/app.getting-started.tsx` | `pip install -e "sdk/python[otel,openai]"` | `pip install "helios-observatory-sdk[otel,openai]"` |
| `src/components/helios/landing-sections.tsx` | `pip install -e "sdk/python[otel]"` | `pip install "helios-observatory-sdk[otel]"` |
| `docs/SELF_SERVICE_ONBOARDING.md` | `pip install -e "sdk/python[otel,openai]"` | `pip install "helios-observatory-sdk[otel,openai]"` |
| `examples/python_sdk_quickstart/requirements.txt` | editable combined SDK | `helios-observatory-sdk[otel,openai]==0.2.0` |
| `examples/rag_support_bot/requirements.txt` | editable base SDK | `helios-observatory-sdk==0.2.0` |
| `docs/SDK_INGESTION.md` | describes the editable demo dependency | describe the pinned PyPI dependency |

After editing, test each example from a clean environment, update screenshots
or copy only if needed, and rerun the complete repository quality gate. Keep
repository-development commands in `README.md`, backend integration tests, and
ordinary CI editable so they continue testing the checked-out source rather
than a previously published package.
