"""Source-level safeguards for the public Python distribution contract."""

from importlib import metadata
from pathlib import Path
import re

from packaging.requirements import Requirement

import helios_sdk


PACKAGE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_METADATA = metadata.metadata("helios-observatory-sdk")


def test_public_package_identity_and_version():
    assert PACKAGE_METADATA["Name"] == "helios-observatory-sdk"
    assert PACKAGE_METADATA["Version"] == "0.2.0"
    assert helios_sdk.__version__ == metadata.version("helios-observatory-sdk") == "0.2.0"
    assert '"0.2.0"' not in (PACKAGE_DIR / "helios_sdk" / "__init__.py").read_text()


def test_python_and_license_metadata():
    assert PACKAGE_METADATA["Requires-Python"] == ">=3.10"
    assert PACKAGE_METADATA["License-Expression"] == "Apache-2.0"
    assert "LICENSE" in PACKAGE_METADATA.get_all("License-File")
    classifiers = set(PACKAGE_METADATA.get_all("Classifier"))
    assert {f"Programming Language :: Python :: 3.{minor}" for minor in range(10, 14)} <= classifiers
    assert "Operating System :: OS Independent" in classifiers
    assert "Typing :: Typed" not in classifiers
    assert "Private :: Do Not Upload" not in classifiers
    assert "License :: Other/Proprietary License" not in classifiers


def test_public_attribution_and_urls():
    assert PACKAGE_METADATA["Author"] == "Roshan Raj"
    assert PACKAGE_METADATA["Maintainer"] == "Roshan Raj"
    project_urls = {
        value.split(", ", 1)[0]: value.split(", ", 1)[1]
        for value in PACKAGE_METADATA.get_all("Project-URL")
    }
    assert project_urls == {
        "Homepage": "https://helios-staging-tau.vercel.app",
        "Repository": "https://github.com/Roshan3580/Helios",
        "Issues": "https://github.com/Roshan3580/Helios/issues",
        "Documentation": "https://github.com/Roshan3580/Helios/tree/main/docs",
    }


def test_base_dependencies_remain_dependency_light():
    requirements = [Requirement(value) for value in PACKAGE_METADATA.get_all("Requires-Dist")]
    base = [requirement for requirement in requirements if requirement.marker is None]
    assert [requirement.name for requirement in base] == ["httpx"]
    assert all(requirement.url is None for requirement in requirements)


def test_runtime_extras_are_independently_installable():
    requirements = [Requirement(value) for value in PACKAGE_METADATA.get_all("Requires-Dist")]

    def names(extra):
        return {
            requirement.name
            for requirement in requirements
            if requirement.marker is not None and requirement.marker.evaluate({"extra": extra})
        }

    otel = {
        "opentelemetry-api",
        "opentelemetry-exporter-otlp-proto-http",
        "opentelemetry-sdk",
    }
    openai = otel | {"openai", "opentelemetry-instrumentation-openai-v2"}
    assert names("otel") == otel
    assert names("openai") == openai
    assert names("all") == openai


def test_repository_and_package_license_texts_match():
    assert (PACKAGE_DIR / "LICENSE").read_bytes() == (REPOSITORY_ROOT / "LICENSE").read_bytes()


def test_manifest_excludes_repository_only_content():
    manifest = (PACKAGE_DIR / "MANIFEST.in").read_text()
    assert "recursive-include helios_sdk *.py" in manifest
    assert "prune tests" in manifest
    assert "include LICENSE" in manifest
    assert "include README.md" in manifest


def test_pypi_readme_has_public_install_shapes_and_absolute_links():
    readme = (PACKAGE_DIR / "README.md").read_text()
    for command in (
        "pip install helios-observatory-sdk",
        'pip install "helios-observatory-sdk[otel]"',
        'pip install "helios-observatory-sdk[openai]"',
        'pip install "helios-observatory-sdk[otel,openai]"',
    ):
        assert command in readme
    assert not re.search(r"!?\[[^]]*\]\((?!https://)[^)]+\)", readme)
    assert "production-capable hosted beta" in readme
    assert "—" not in readme


def test_public_readme_documents_security_and_delivery_semantics():
    readme = (PACKAGE_DIR / "README.md").read_text()
    assert "Never commit a `hel_proj_*`" in readme
    assert "does not prove that the backend accepted the trace" in readme
    assert "revoked project key remains rejected by Helios with HTTP 401" in readme


def test_release_helpers_cannot_publish():
    for name in (
        "build-python-sdk-release.sh",
        "validate-python-sdk-artifacts.py",
        "smoke-python-sdk-install.py",
    ):
        helper = (REPOSITORY_ROOT / "scripts" / name).read_text()
        assert "twine upload" not in helper
        assert "pypa/gh-action-pypi-publish" not in helper
        assert "PYPI_API_TOKEN" not in helper


def test_publishing_workflow_is_release_only_and_uses_oidc():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "publish-python-sdk.yml").read_text()
    trigger = workflow.split("permissions:", 1)[0]
    assert "release:" in trigger
    assert "types: [published]" in trigger
    assert "pull_request:" not in trigger
    assert "push:" not in trigger
    assert "workflow_dispatch:" not in trigger
    assert workflow.count("id-token: write") == 1
    assert "name: pypi" in workflow
    assert "PYPI_API_TOKEN" not in workflow
    assert "skip-existing: false" in workflow
    assert "attestations: true" in workflow
    assert re.search(r"pypa/gh-action-pypi-publish@[0-9a-f]{40}", workflow)


def test_ordinary_ci_validates_every_supported_python_without_oidc():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    sdk_job = workflow.split("  sdk-tests:", 1)[1].split("\n  typescript-sdk:", 1)[0]
    assert 'python-version: ["3.10", "3.11", "3.12", "3.13"]' in sdk_job
    assert "bash scripts/build-python-sdk-release.sh" in sdk_job
    assert "id-token: write" not in sdk_job
    assert "pypa/gh-action-pypi-publish" not in sdk_job
