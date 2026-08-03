#!/usr/bin/env python3
"""Validate Python SDK distributions without publishing them."""

from __future__ import annotations

import argparse
import email
import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


DIST_NAME = "helios-observatory-sdk"
IMPORT_NAME = "helios_sdk"
EXPECTED_PYTHON = ">=3.10"
EXPECTED_LICENSE = "Apache-2.0"
EXPECTED_EXTRAS = {"all", "dev", "openai", "otel"}
EXPECTED_URLS = {
    "Homepage": "https://helios-staging-tau.vercel.app",
    "Repository": "https://github.com/Roshan3580/Helios",
    "Issues": "https://github.com/Roshan3580/Helios/issues",
    "Documentation": "https://github.com/Roshan3580/Helios/tree/main/docs",
}

FORBIDDEN_MEMBER_PARTS = {
    ".env",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "tests",
}
SECRET_PATTERNS = {
    "generated-looking Helios project key": re.compile(
        rb"hel_proj_[0-9a-fA-F]{16}_[A-Za-z0-9_-]{40,}"
    ),
    "OpenAI-style secret": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "GitHub-style token": re.compile(rb"gh[oprsu]_[A-Za-z0-9]{32,}"),
    "bearer token": re.compile(rb"Bearer[ \t]+[A-Za-z0-9._~-]{24,}"),
    "database URL": re.compile(
        rb"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s\"'<>]+",
        re.IGNORECASE,
    ),
    "absolute user path": re.compile(
        rb"(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)"
    ),
}


def fail(message: str) -> None:
    raise SystemExit(f"artifact validation failed: {message}")


def safe_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        fail(f"unsafe archive member path: {name!r}")
    if any(part in FORBIDDEN_MEMBER_PARTS or part.startswith(".env") for part in path.parts):
        fail(f"forbidden archive member: {name}")
    return path


def scan_bytes(label: str, data: bytes) -> None:
    for description, pattern in SECRET_PATTERNS.items():
        if pattern.search(data):
            fail(f"{description} found in {label}")


def require_exact_artifacts(dist_dir: Path, version: str) -> tuple[Path, Path]:
    wheel = dist_dir / f"helios_observatory_sdk-{version}-py3-none-any.whl"
    sdist = dist_dir / f"helios_observatory_sdk-{version}.tar.gz"
    actual = {path.name for path in dist_dir.iterdir() if path.is_file()}
    expected = {wheel.name, sdist.name}
    if actual != expected:
        fail(f"expected exactly {sorted(expected)}, found {sorted(actual)}")
    return wheel, sdist


def parse_metadata(raw: bytes):
    return email.message_from_bytes(raw)


def validate_metadata(raw: bytes, version: str) -> None:
    message = parse_metadata(raw)
    if canonicalize_name(message["Name"]) != canonicalize_name(DIST_NAME):
        fail(f"unexpected distribution name: {message['Name']!r}")
    if message["Version"] != version:
        fail(f"metadata version {message['Version']!r} does not equal {version!r}")
    if message["Requires-Python"] != EXPECTED_PYTHON:
        fail(f"unexpected Requires-Python: {message['Requires-Python']!r}")
    if message["License-Expression"] != EXPECTED_LICENSE:
        fail(f"unexpected License-Expression: {message['License-Expression']!r}")
    if "LICENSE" not in (message.get_all("License-File") or []):
        fail("metadata does not declare LICENSE")
    if message["Description-Content-Type"] != "text/markdown":
        fail("long description is not declared as Markdown")

    classifiers = set(message.get_all("Classifier") or [])
    forbidden_classifiers = {
        "Private :: Do Not Upload",
        "License :: Other/Proprietary License",
        "Typing :: Typed",
    }
    found_forbidden = classifiers & forbidden_classifiers
    if found_forbidden:
        fail(f"forbidden classifiers present: {sorted(found_forbidden)}")
    for minor in range(10, 14):
        required = f"Programming Language :: Python :: 3.{minor}"
        if required not in classifiers:
            fail(f"missing classifier {required!r}")

    urls: dict[str, str] = {}
    for value in message.get_all("Project-URL") or []:
        label, separator, url = value.partition(", ")
        if not separator:
            fail(f"malformed Project-URL: {value!r}")
        urls[label] = url
    if urls != EXPECTED_URLS:
        fail(f"project URLs differ: {urls!r}")

    extras = set(message.get_all("Provides-Extra") or [])
    if extras != EXPECTED_EXTRAS:
        fail(f"unexpected extras: {sorted(extras)}")

    requirements = [Requirement(value) for value in message.get_all("Requires-Dist") or []]
    base = {canonicalize_name(req.name) for req in requirements if req.marker is None}
    if base != {"httpx"}:
        fail(f"base dependencies must contain only httpx, found {sorted(base)}")
    for requirement in requirements:
        if requirement.url:
            fail(f"direct URL dependency is not allowed: {requirement}")

    def names_for_extra(extra: str) -> set[str]:
        return {
            canonicalize_name(req.name)
            for req in requirements
            if req.marker is not None and req.marker.evaluate({"extra": extra})
        }

    otel_names = {
        "opentelemetry-api",
        "opentelemetry-exporter-otlp-proto-http",
        "opentelemetry-sdk",
    }
    openai_names = otel_names | {"openai", "opentelemetry-instrumentation-openai-v2"}
    if names_for_extra("otel") != otel_names:
        fail(f"unexpected otel dependencies: {sorted(names_for_extra('otel'))}")
    if names_for_extra("openai") != openai_names:
        fail(f"unexpected openai dependencies: {sorted(names_for_extra('openai'))}")
    if names_for_extra("all") != openai_names:
        fail(f"unexpected all dependencies: {sorted(names_for_extra('all'))}")


def validate_wheel(wheel: Path, package_dir: Path, version: str, license_text: bytes) -> None:
    dist_info = f"helios_observatory_sdk-{version}.dist-info"
    module_files = {f"{IMPORT_NAME}/{path.name}" for path in (package_dir / IMPORT_NAME).glob("*.py")}
    expected = module_files | {
        f"{dist_info}/METADATA",
        f"{dist_info}/RECORD",
        f"{dist_info}/WHEEL",
        f"{dist_info}/licenses/LICENSE",
        f"{dist_info}/top_level.txt",
    }

    with zipfile.ZipFile(wheel) as archive:
        actual = set(archive.namelist())
        for info in archive.infolist():
            safe_member_name(info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                fail(f"wheel contains symbolic link: {info.filename}")
            scan_bytes(f"{wheel.name}:{info.filename}", archive.read(info))
        if actual != expected:
            fail(
                "wheel contents differ from the allowlist: "
                f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
            )
        metadata = archive.read(f"{dist_info}/METADATA")
        validate_metadata(metadata, version)
        wheel_metadata = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
        if "Root-Is-Purelib: true" not in wheel_metadata or "Tag: py3-none-any" not in wheel_metadata:
            fail("wheel is not marked as pure Python py3-none-any")
        if archive.read(f"{dist_info}/licenses/LICENSE") != license_text:
            fail("wheel license differs from the repository license")


def validate_sdist(sdist: Path, package_dir: Path, version: str, license_text: bytes) -> None:
    root = f"helios_observatory_sdk-{version}"
    module_files = {f"{root}/{IMPORT_NAME}/{path.name}" for path in (package_dir / IMPORT_NAME).glob("*.py")}
    egg_info = f"{root}/helios_observatory_sdk.egg-info"
    expected_files = module_files | {
        f"{root}/LICENSE",
        f"{root}/MANIFEST.in",
        f"{root}/PKG-INFO",
        f"{root}/README.md",
        f"{root}/pyproject.toml",
        f"{root}/setup.cfg",
        f"{egg_info}/PKG-INFO",
        f"{egg_info}/SOURCES.txt",
        f"{egg_info}/dependency_links.txt",
        f"{egg_info}/requires.txt",
        f"{egg_info}/top_level.txt",
    }
    expected_dirs = {root, f"{root}/{IMPORT_NAME}", egg_info}

    actual_files: set[str] = set()
    actual_dirs: set[str] = set()
    with tarfile.open(sdist, mode="r:gz") as archive:
        for member in archive.getmembers():
            safe_member_name(member.name)
            if member.issym() or member.islnk():
                fail(f"sdist contains link: {member.name}")
            if member.isdir():
                actual_dirs.add(member.name)
                continue
            if not member.isfile():
                fail(f"sdist contains unsupported member type: {member.name}")
            actual_files.add(member.name)
            extracted = archive.extractfile(member)
            if extracted is None:
                fail(f"could not read sdist member: {member.name}")
            scan_bytes(f"{sdist.name}:{member.name}", extracted.read())
        if actual_files != expected_files or actual_dirs != expected_dirs:
            fail(
                "sdist contents differ from the allowlist: "
                f"missing_files={sorted(expected_files - actual_files)}, "
                f"unexpected_files={sorted(actual_files - expected_files)}, "
                f"missing_dirs={sorted(expected_dirs - actual_dirs)}, "
                f"unexpected_dirs={sorted(actual_dirs - expected_dirs)}"
            )
        license_member = archive.extractfile(f"{root}/LICENSE")
        if license_member is None or license_member.read() != license_text:
            fail("sdist license differs from the repository license")
        metadata_member = archive.extractfile(f"{root}/PKG-INFO")
        if metadata_member is None:
            fail("sdist PKG-INFO is missing")
        validate_metadata(metadata_member.read(), version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    dist_dir = args.dist_dir.resolve(strict=True)
    package_dir = args.package_dir.resolve(strict=True)
    repository_root = args.repository_root.resolve(strict=True)
    package_license = (package_dir / "LICENSE").read_bytes()
    repository_license = (repository_root / "LICENSE").read_bytes()
    if package_license != repository_license:
        fail("sdk/python/LICENSE differs from the repository LICENSE")

    wheel, sdist = require_exact_artifacts(dist_dir, args.version)
    validate_wheel(wheel, package_dir, args.version, repository_license)
    validate_sdist(sdist, package_dir, args.version, repository_license)
    print(f"Validated wheel: {wheel.name}")
    print(f"Validated sdist: {sdist.name}")
    print(
        f"Metadata: helios-observatory-sdk {args.version}, "
        "Python >=3.10, Apache-2.0"
    )
    print("Contents and secret scan: passed")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        fail(str(exc))
