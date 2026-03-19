#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALL_RUNNER="${ROOT_DIR}/scripts/run_docker_fuzz_all.sh"
ENSURE_IMAGE_SCRIPT="${ROOT_DIR}/scripts/ensure_provenance_image.sh"
DEFAULT_OUT_ROOT="${ROOT_DIR}/agent/verify/long_runs"

print_usage() {
  cat <<'EOF'
Usage:
  run_docker_fuzz_all_10_combinations.sh --image <name> [options]

Required:
  --image <name>                  Docker image to use for all 10 runs

Options:
  --run-hours <int>               Fuzzer --run_time for each combination. Default: 1
  --fuzzing-loop <int>            Fuzzer --fuzzing_loop. Default: -1
  --out-root <dir>                Host output root. Default: agent/verify/long_runs
  --label <text>                  Extra suffix for the top-level batch and child batches
  --exercise-guided-explore-ratio <float>
                                  Optional override for --exercise_guided_explore_ratio
  --skip-image-ensure             Do not verify/build the image before running
  --rebuild-image                 Force rebuild of the input image before running
  --keep-going                    Continue after failures and attempt all 10 combinations
  --dry-run                       Print planned child invocations and exit
  --help                          Show this help

Behavior:
  - Runs exactly 10 combinations: 5 projects x 2 modes
  - Mode 1: ECFuzz original => tracking off, use-backed off
  - Mode 2: ECFuzz+ParamTracking => tracking on, use-backed on
  - Unit tests remain enabled because the underlying runner always uses:
      --skip_unit_test=False
      --require_unit_pass_for_system_test=True
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

IMAGE_NAME=""
RUN_HOURS="1"
FUZZING_LOOP="-1"
OUT_ROOT="${DEFAULT_OUT_ROOT}"
LABEL=""
EXPLORE_RATIO=""
ENSURE_IMAGE="true"
REBUILD_IMAGE="false"
KEEP_GOING="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      require_value "$1" "${2:-}"
      IMAGE_NAME="$2"
      shift 2
      ;;
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

if [[ -z "${IMAGE_NAME}" ]]; then
  echo "--image is required" >&2
  print_usage >&2
  exit 1
fi

if ! [[ "${RUN_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "--run-hours must be a non-negative integer" >&2
  exit 1
fi

if ! [[ "${FUZZING_LOOP}" =~ ^-?[0-9]+$ ]]; then
  echo "--fuzzing-loop must be an integer" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SAFE_LABEL=""
if [[ -n "${LABEL}" ]]; then
  SAFE_LABEL="-$(printf '%s' "${LABEL}" | tr -cs 'A-Za-z0-9._-' '-')"
fi

MASTER_ROOT="${OUT_ROOT}/batch-${TIMESTAMP}-all10${SAFE_LABEL}"
CHILD_OUT_ROOT="${MASTER_ROOT}/runs"
LOG_DIR="${MASTER_ROOT}/logs"
SUMMARY_FILE="${MASTER_ROOT}/summary.tsv"
MODE_SUMMARY_FILE="${MASTER_ROOT}/mode_summary.tsv"
MANIFEST_FILE="${MASTER_ROOT}/manifest.txt"

mkdir -p "${CHILD_OUT_ROOT}" "${LOG_DIR}"

{
  echo -e "mode\ttracking_mode\tuse_backed\tproject\tstatus\tcase_root\tlog_file\tchild_batch_root"
} >"${SUMMARY_FILE}"

{
  echo -e "mode\ttracking_mode\tuse_backed\tstatus\tchild_batch_root\tlog_file"
} >"${MODE_SUMMARY_FILE}"

{
  echo "batch_type=all_10_combinations"
  echo "image=${IMAGE_NAME}"
  echo "run_hours=${RUN_HOURS}"
  echo "fuzzing_loop=${FUZZING_LOOP}"
  echo "out_root=${OUT_ROOT}"
  echo "child_out_root=${CHILD_OUT_ROOT}"
  echo "keep_going=${KEEP_GOING}"
  echo "dry_run=${DRY_RUN}"
  echo "mode_1=ecfuzz-original tracking=off use_backed=off"
  echo "mode_2=ecfuzz-paramtracking tracking=on use_backed=on"
} >"${MANIFEST_FILE}"

if [[ "${DRY_RUN}" != "true" ]] && [[ "${ENSURE_IMAGE}" == "true" ]]; then
  ensure_cmd=("${ENSURE_IMAGE_SCRIPT}" "--image" "${IMAGE_NAME}" "--quiet")
  if [[ "${REBUILD_IMAGE}" == "true" ]]; then
    ensure_cmd+=("--rebuild")
  fi
  "${ensure_cmd[@]}"
fi

find_child_batch_root() {
  local mode_log="$1"
  local child_batch_root=""
  child_batch_root="$(awk -F= '/^batch_root=/{print $2}' "${mode_log}" | tail -n 1)"
  if [[ -n "${child_batch_root}" ]]; then
    printf '%s\n' "${child_batch_root}"
    return 0
  fi

  child_batch_root="$(ls -1dt "${CHILD_OUT_ROOT}"/batch-* 2>/dev/null | head -n 1 || true)"
  printf '%s\n' "${child_batch_root}"
}

aggregate_child_summary() {
  local mode_name="$1"
  local tracking_mode="$2"
  local use_backed="$3"
  local child_batch_root="$4"
  local child_summary="${child_batch_root}/summary.tsv"
  local row_status="ok"

  if [[ ! -f "${child_summary}" ]]; then
    if [[ "${DRY_RUN}" != "true" ]]; then
      row_status="failed"
    fi
    printf '%s\n' "${row_status}"
    return 0
  fi

  while IFS=$'\t' read -r project status case_root log_file; do
    [[ -n "${project}" ]] || continue
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
      "${mode_name}" \
      "${tracking_mode}" \
      "${use_backed}" \
      "${project}" \
      "${status}" \
      "${case_root}" \
      "${log_file}" \
      "${child_batch_root}" >>"${SUMMARY_FILE}"
    if [[ "${status}" != "ok" ]]; then
      row_status="failed"
    fi
  done < <(tail -n +2 "${child_summary}")

  printf '%s\n' "${row_status}"
}

MODE_NAMES=(ecfuzz-original ecfuzz-paramtracking)
MODE_TRACKING=(off on)
MODE_USE_BACKED=(off on)

overall_failed="false"

for idx in "${!MODE_NAMES[@]}"; do
  mode_name="${MODE_NAMES[$idx]}"
  tracking_mode="${MODE_TRACKING[$idx]}"
  use_backed="${MODE_USE_BACKED[$idx]}"
  child_label="${mode_name}"
  mode_log="${LOG_DIR}/${mode_name}.log"
  mode_status="ok"

  if [[ -n "${LABEL}" ]]; then
    child_label="${mode_name}-${LABEL}"
  fi

  cmd=(
    "${ALL_RUNNER}"
    "--run-hours" "${RUN_HOURS}"
    "--fuzzing-loop" "${FUZZING_LOOP}"
    "--tracking-mode" "${tracking_mode}"
    "--use-backed" "${use_backed}"
    "--image" "${IMAGE_NAME}"
    "--out-root" "${CHILD_OUT_ROOT}"
    "--label" "${child_label}"
    "--skip-image-ensure"
  )

  if [[ -n "${EXPLORE_RATIO}" ]]; then
    cmd+=("--exercise-guided-explore-ratio" "${EXPLORE_RATIO}")
  fi
  if [[ "${KEEP_GOING}" == "true" ]]; then
    cmd+=("--keep-going")
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    cmd+=("--dry-run")
  fi

  child_rc=0
  if ! "${cmd[@]}" 2>&1 | tee "${mode_log}"; then
    child_rc=1
    mode_status="failed"
  fi

  child_batch_root="$(find_child_batch_root "${mode_log}")"
  aggregate_status="$(aggregate_child_summary "${mode_name}" "${tracking_mode}" "${use_backed}" "${child_batch_root}")"
  if [[ "${aggregate_status}" != "ok" ]]; then
    mode_status="failed"
  fi

  printf "%s\t%s\t%s\t%s\t%s\t%s\n" \
    "${mode_name}" \
    "${tracking_mode}" \
    "${use_backed}" \
    "${mode_status}" \
    "${child_batch_root}" \
    "${mode_log}" >>"${MODE_SUMMARY_FILE}"

  if [[ "${mode_status}" != "ok" ]]; then
    overall_failed="true"
  fi

  if [[ "${child_rc}" -ne 0 ]] && [[ "${KEEP_GOING}" != "true" ]]; then
    echo "batch_root=${MASTER_ROOT}"
    exit 1
  fi
done

echo "batch_root=${MASTER_ROOT}"

if [[ "${overall_failed}" == "true" ]] && [[ "${DRY_RUN}" != "true" ]]; then
  exit 1
fi
