#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SINGLE_RUNNER="${ROOT_DIR}/scripts/run_docker_fuzz_single.sh"
ENSURE_IMAGE_SCRIPT="${ROOT_DIR}/scripts/ensure_provenance_image.sh"
DEFAULT_OUT_ROOT="${ROOT_DIR}/agent/verify/long_runs"
PROJECTS=(hadoop-common hadoop-hdfs hbase zookeeper alluxio)

print_usage() {
  cat <<'EOF'
Usage:
  run_docker_fuzz_all.sh [options]

Options:
  --run-hours <int>               Fuzzer --run_time for each project. Default: 1
  --fuzzing-loop <int>            Fuzzer --fuzzing_loop for each project. Default: -1
  --tracking-mode <on|off>        Map to --exercise_guided_mutation. Default: off
  --guided <on|off>               Alias for --tracking-mode
  --use-backed <on|off|noop>      Provenance mode. Default: off
  --image <name>                  Docker image. Default: ecfuzz/ecfuzz-provenance-agent:local
  --out-root <dir>                Output root. Default: agent/verify/long_runs
  --label <text>                  Extra suffix for the batch directory and child cases
  --exercise-guided-explore-ratio <float>
                                  Optional override for --exercise_guided_explore_ratio
  --projects "<p1> <p2> ..."      Space-separated project list. Default: all 5
  --skip-image-ensure             Do not auto-build the docker image if missing
  --rebuild-image                 Force rebuild of the docker image before the batch
  --keep-going                    Continue after a project failure
  --dry-run                       Print planned child invocations and exit
  --help                          Show this help

Behavior:
  - Runs projects sequentially
  - Uses run_docker_fuzz_single.sh underneath
  - Unit tests are always enabled with strict pass gating
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

normalize_on_off() {
  local name="$1"
  local value="$2"
  case "${value}" in
    on|off)
      printf '%s\n' "${value}"
      ;;
    *)
      echo "invalid ${name}: ${value}; expected on/off" >&2
      exit 1
      ;;
  esac
}

normalize_use_backed() {
  local value="$1"
  case "${value}" in
    on|off|noop)
      printf '%s\n' "${value}"
      ;;
    *)
      echo "invalid --use-backed: ${value}; expected on/off/noop" >&2
      exit 1
      ;;
  esac
}

validate_project() {
  local candidate="$1"
  local project
  for project in "${PROJECTS[@]}"; do
    if [[ "${project}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

RUN_HOURS="1"
FUZZING_LOOP="-1"
TRACKING_MODE="off"
USE_BACKED="off"
IMAGE_NAME="ecfuzz/ecfuzz-provenance-agent:local"
OUT_ROOT="${DEFAULT_OUT_ROOT}"
LABEL=""
EXPLORE_RATIO=""
KEEP_GOING="false"
DRY_RUN="false"
RUN_PROJECTS=("${PROJECTS[@]}")
ENSURE_IMAGE="true"
REBUILD_IMAGE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-hours)
      require_value "$1" "${2:-}"
      RUN_HOURS="$2"
      shift 2
      ;;
    --fuzzing-loop)
      require_value "$1" "${2:-}"
      FUZZING_LOOP="$2"
      shift 2
      ;;
    --tracking-mode|--guided)
      require_value "$1" "${2:-}"
      TRACKING_MODE="$(normalize_on_off "$1" "$2")"
      shift 2
      ;;
    --use-backed)
      require_value "$1" "${2:-}"
      USE_BACKED="$(normalize_use_backed "$2")"
      shift 2
      ;;
    --image)
      require_value "$1" "${2:-}"
      IMAGE_NAME="$2"
      shift 2
      ;;
    --out-root)
      require_value "$1" "${2:-}"
      OUT_ROOT="$2"
      shift 2
      ;;
    --label)
      require_value "$1" "${2:-}"
      LABEL="$2"
      shift 2
      ;;
    --exercise-guided-explore-ratio)
      require_value "$1" "${2:-}"
      EXPLORE_RATIO="$2"
      shift 2
      ;;
    --projects)
      require_value "$1" "${2:-}"
      IFS=' ' read -r -a RUN_PROJECTS <<<"$2"
      shift 2
      ;;
    --skip-image-ensure)
      ENSURE_IMAGE="false"
      shift
      ;;
    --rebuild-image)
      REBUILD_IMAGE="true"
      shift
      ;;
    --keep-going)
      KEEP_GOING="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
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

if ! [[ "${RUN_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "--run-hours must be a non-negative integer" >&2
  exit 1
fi

if ! [[ "${FUZZING_LOOP}" =~ ^-?[0-9]+$ ]]; then
  echo "--fuzzing-loop must be an integer" >&2
  exit 1
fi

if [[ ${#RUN_PROJECTS[@]} -eq 0 ]]; then
  echo "--projects produced an empty project list" >&2
  exit 1
fi

for project in "${RUN_PROJECTS[@]}"; do
  if ! validate_project "${project}"; then
    echo "invalid project in --projects: ${project}" >&2
    exit 1
  fi
done

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SAFE_LABEL=""
if [[ -n "${LABEL}" ]]; then
  SAFE_LABEL="-$(printf '%s' "${LABEL}" | tr -cs 'A-Za-z0-9._-' '-')"
fi

BATCH_ROOT="${OUT_ROOT}/batch-${TIMESTAMP}${SAFE_LABEL}"
LOG_DIR="${BATCH_ROOT}/logs"
SUMMARY_FILE="${BATCH_ROOT}/summary.tsv"

mkdir -p "${LOG_DIR}"

{
  echo -e "project\tstatus\tcase_root\tlog_file"
} >"${SUMMARY_FILE}"

if [[ "${DRY_RUN}" != "true" ]] && [[ "${ENSURE_IMAGE}" == "true" ]]; then
  ensure_cmd=("${ENSURE_IMAGE_SCRIPT}" "--image" "${IMAGE_NAME}" "--quiet")
  if [[ "${REBUILD_IMAGE}" == "true" ]]; then
    ensure_cmd+=("--rebuild")
  fi
  "${ensure_cmd[@]}"
fi

for project in "${RUN_PROJECTS[@]}"; do
  project_log="${LOG_DIR}/${project}.log"
  cmd=(
    "${SINGLE_RUNNER}"
    "--project" "${project}"
    "--run-hours" "${RUN_HOURS}"
    "--fuzzing-loop" "${FUZZING_LOOP}"
    "--tracking-mode" "${TRACKING_MODE}"
    "--use-backed" "${USE_BACKED}"
    "--image" "${IMAGE_NAME}"
    "--out-root" "${BATCH_ROOT}"
  )
  if [[ -n "${LABEL}" ]]; then
    cmd+=("--label" "${LABEL}")
  fi
  if [[ -n "${EXPLORE_RATIO}" ]]; then
    cmd+=("--exercise-guided-explore-ratio" "${EXPLORE_RATIO}")
  fi
  if [[ "${ENSURE_IMAGE}" != "true" ]]; then
    cmd+=("--skip-image-ensure")
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    cmd+=("--dry-run")
  fi

  status="ok"
  case_root=""
  if ! "${cmd[@]}" 2>&1 | tee "${project_log}"; then
    status="failed"
    if [[ "${KEEP_GOING}" != "true" ]]; then
      case_root="$(awk -F= '/^case_root=/{print $2}' "${project_log}" | tail -n 1)"
      printf "%s\t%s\t%s\t%s\n" "${project}" "${status}" "${case_root}" "${project_log}" >>"${SUMMARY_FILE}"
      echo "batch_root=${BATCH_ROOT}"
      exit 1
    fi
  fi

  case_root="$(awk -F= '/^case_root=/{print $2}' "${project_log}" | tail -n 1)"
  printf "%s\t%s\t%s\t%s\n" "${project}" "${status}" "${case_root}" "${project_log}" >>"${SUMMARY_FILE}"
done

echo "batch_root=${BATCH_ROOT}"
