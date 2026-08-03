#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
readonly PACKAGE_DIR="${REPOSITORY_ROOT}/sdk/python"
readonly DIST_DIR="${PACKAGE_DIR}/dist"
readonly PYTHON_REQUEST="${PYTHON_BIN:-python3}"
TEMP_BASE="${TMPDIR:-/tmp}"
readonly TEMP_BASE="${TEMP_BASE%/}"

safe_remove_generated_directory() {
  local target="$1"
  local expected_parent="$2"
  local parent
  local name

  parent="$(cd "$(dirname "${target}")" && pwd -P)"
  name="$(basename "${target}")"
  if [[ "${parent}" != "${expected_parent}" ]]; then
    echo "Refusing to clean unexpected parent: ${parent}" >&2
    exit 1
  fi
  case "${name}" in
    build|dist|helios_observatory_sdk.egg-info|helios_sdk.egg-info) ;;
    *)
      echo "Refusing to clean unexpected generated directory: ${name}" >&2
      exit 1
      ;;
  esac
  if [[ -L "${target}" ]]; then
    echo "Refusing to clean symbolic link: ${target}" >&2
    exit 1
  fi
  if [[ -e "${target}" ]]; then
    if [[ ! -d "${target}" ]]; then
      echo "Refusing to clean non-directory: ${target}" >&2
      exit 1
    fi
    rm -rf -- "${target}"
  fi
}

safe_remove_scratch() {
  if [[ -z "${SCRATCH_DIR:-}" || ! -e "${SCRATCH_DIR}" ]]; then
    return
  fi
  if [[ -L "${SCRATCH_DIR}" || ! -d "${SCRATCH_DIR}" ]]; then
    echo "Refusing to clean invalid scratch directory: ${SCRATCH_DIR}" >&2
    return 1
  fi
  case "${SCRATCH_DIR}" in
    "${TEMP_BASE}"/helios-python-release.*) ;;
    *)
      echo "Refusing to clean unexpected scratch directory: ${SCRATCH_DIR}" >&2
      return 1
      ;;
  esac
  rm -rf -- "${SCRATCH_DIR}"
}

install_and_smoke() {
  local environment_name="$1"
  local shape="$2"
  local requirement="$3"
  local environment_dir="${SCRATCH_DIR}/${environment_name}"

  "${PYTHON_BIN}" -m venv "${environment_dir}"
  "${environment_dir}/bin/python" -m pip install --disable-pip-version-check "${requirement}"
  "${environment_dir}/bin/python" -m pip check
  "${environment_dir}/bin/python" "${SCRIPT_DIR}/smoke-python-sdk-install.py" \
    --shape "${shape}" --version "${EXPECTED_VERSION}"
}

if [[ ! -d "${PACKAGE_DIR}/helios_sdk" || ! -f "${PACKAGE_DIR}/pyproject.toml" ]]; then
  echo "Python SDK package directory is incomplete: ${PACKAGE_DIR}" >&2
  exit 1
fi
if ! PYTHON_BIN="$(command -v "${PYTHON_REQUEST}")"; then
  echo "Python interpreter not found: ${PYTHON_REQUEST}" >&2
  exit 1
fi
if [[ "${PYTHON_BIN}" != /* ]]; then
  PYTHON_BIN="$(cd "$(dirname "${PYTHON_BIN}")" && pwd -P)/$(basename "${PYTHON_BIN}")"
fi
readonly PYTHON_BIN
PACKAGE_VERSION="$("${PYTHON_BIN}" -c 'import pathlib, re, sys; text = pathlib.Path(sys.argv[1]).read_text(); match = re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"\s*$", text); print(match.group(1) if match else "")' "${PACKAGE_DIR}/pyproject.toml")"
if [[ -z "${PACKAGE_VERSION}" ]]; then
  echo "Could not read the package version from sdk/python/pyproject.toml." >&2
  exit 1
fi
readonly EXPECTED_VERSION="${EXPECTED_VERSION:-${PACKAGE_VERSION}}"
if [[ "${PACKAGE_VERSION}" != "${EXPECTED_VERSION}" ]]; then
  echo "Package version ${PACKAGE_VERSION} does not match expected version ${EXPECTED_VERSION}." >&2
  exit 1
fi

safe_remove_generated_directory "${PACKAGE_DIR}/build" "${PACKAGE_DIR}"
safe_remove_generated_directory "${PACKAGE_DIR}/dist" "${PACKAGE_DIR}"
safe_remove_generated_directory "${PACKAGE_DIR}/helios_observatory_sdk.egg-info" "${PACKAGE_DIR}"
safe_remove_generated_directory "${PACKAGE_DIR}/helios_sdk.egg-info" "${PACKAGE_DIR}"

(
  cd "${PACKAGE_DIR}"
  "${PYTHON_BIN}" -m build
)

readonly WHEEL="${DIST_DIR}/helios_observatory_sdk-${EXPECTED_VERSION}-py3-none-any.whl"
readonly SDIST="${DIST_DIR}/helios_observatory_sdk-${EXPECTED_VERSION}.tar.gz"
"${PYTHON_BIN}" -m twine check "${WHEEL}" "${SDIST}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/validate-python-sdk-artifacts.py" \
  --dist-dir "${DIST_DIR}" \
  --package-dir "${PACKAGE_DIR}" \
  --repository-root "${REPOSITORY_ROOT}" \
  --version "${EXPECTED_VERSION}"

SCRATCH_DIR="$(mktemp -d "${TEMP_BASE}/helios-python-release.XXXXXX")"
readonly SCRATCH_DIR
trap safe_remove_scratch EXIT

install_and_smoke "wheel-base" "base" "${WHEEL}"
install_and_smoke "wheel-otel" "otel" "${WHEEL}[otel]"
install_and_smoke "wheel-openai" "openai" "${WHEEL}[openai]"
install_and_smoke "wheel-combined" "combined" "${WHEEL}[otel,openai]"

readonly SDIST_WHEEL_DIR="${SCRATCH_DIR}/sdist-wheel"
mkdir "${SDIST_WHEEL_DIR}"
readonly SDIST_BUILD_ENV="${SCRATCH_DIR}/sdist-build"
"${PYTHON_BIN}" -m venv "${SDIST_BUILD_ENV}"
"${SDIST_BUILD_ENV}/bin/python" -m pip wheel --disable-pip-version-check \
  --no-deps --wheel-dir "${SDIST_WHEEL_DIR}" "${SDIST}"
readonly SDIST_WHEEL="${SDIST_WHEEL_DIR}/helios_observatory_sdk-${EXPECTED_VERSION}-py3-none-any.whl"
if [[ ! -f "${SDIST_WHEEL}" ]]; then
  echo "The sdist did not produce the expected wheel: ${SDIST_WHEEL}" >&2
  exit 1
fi
install_and_smoke "sdist-base" "base" "${SDIST_WHEEL}"

echo "Python SDK release validation passed. No package was published."
