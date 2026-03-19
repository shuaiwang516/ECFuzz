#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_IMAGE="ecfuzz/ecfuzz-provenance-agent:local"
DOCKERFILE_PATH="${ROOT_DIR}/docker/param_tracking/Dockerfile"

print_usage() {
  cat <<'EOF'
Usage:
  ensure_provenance_image.sh [options]

Options:
  --image <name>      Target image tag. Default: ecfuzz/ecfuzz-provenance-agent:local
  --rebuild           Force a rebuild even if the image already exists
  --quiet             Suppress the final status line
  --help              Show this help

Behavior:
  - Verifies docker CLI and daemon availability
  - Builds the provenance-agent image from the current repository tree when missing
  - Uses docker/param_tracking/Dockerfile
EOF
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "${value}" ]]; then
    echo "missing value for ${flag}" >&2
    exit 1
  fi
}

IMAGE_NAME="${DEFAULT_IMAGE}"
REBUILD="false"
QUIET="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      require_value "$1" "${2:-}"
      IMAGE_NAME="$2"
      shift 2
      ;;
    --rebuild)
      REBUILD="true"
      shift
      ;;
    --quiet)
      QUIET="true"
      shift
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not on PATH" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not reachable" >&2
  exit 1
fi

if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  echo "dockerfile not found: ${DOCKERFILE_PATH}" >&2
  exit 1
fi

if [[ "${REBUILD}" != "true" ]] && docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  if [[ "${QUIET}" != "true" ]]; then
    echo "image_ready=${IMAGE_NAME}"
  fi
  exit 0
fi

docker build -t "${IMAGE_NAME}" -f "${DOCKERFILE_PATH}" "${ROOT_DIR}"

if [[ "${QUIET}" != "true" ]]; then
  echo "image_ready=${IMAGE_NAME}"
fi
