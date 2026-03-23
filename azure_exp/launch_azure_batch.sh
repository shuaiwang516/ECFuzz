#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
ROOT_PREFLIGHT_SCRIPT="${SCRIPT_DIR}/remote_root_preflight.sh"

print_usage() {
  cat <<EOF
Usage:
  launch_azure_batch.sh --assignments <file> [options]

Required:
  --assignments <file>            TSV covering all 10 (project, mode) combinations exactly once

Options:
  --machine-list <file>           Inventory file. Default: ${DEFAULT_MACHINE_LIST_FILE}
  --batch-id <text>               Batch identifier used in remote assignment ids
  --parallelism <int>             Concurrent remote launches. Default: 10
  --shared-results-root <path>    Remote shared results root. Default: ${DEFAULT_REMOTE_SHARED_RESULTS_ROOT}
  --dry-run                       Validate config and print the resolved launch plan without SSH
  --help                          Show this help

Behavior:
  - Reads machine_list.txt lines as full SSH commands
  - Maps assignments by 1-based machine line number
  - Launches exactly one (project, mode) run per assigned VM
  - Preflights root access on each machine before bootstrap
  - Streams remote_bootstrap_and_run.sh over SSH; no reliance on run_docker_fuzz_all.sh
  - Both modes explicitly use unit tests via the verified single-run wrapper
  - Publishes each finished assignment directory to the configured shared results root
EOF
}

MACHINE_LIST_FILE="${DEFAULT_MACHINE_LIST_FILE}"
ASSIGNMENTS_FILE=""
BATCH_ID="cloudlab-$(date -u +%Y%m%d-%H%M%S)"
PARALLELISM="10"
SHARED_RESULTS_ROOT="${DEFAULT_REMOTE_SHARED_RESULTS_ROOT}"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --machine-list)
      require_value "$1" "${2:-}"
      MACHINE_LIST_FILE="$2"
      shift 2
      ;;
    --assignments)
      require_value "$1" "${2:-}"
      ASSIGNMENTS_FILE="$2"
      shift 2
      ;;
    --batch-id)
      require_value "$1" "${2:-}"
      BATCH_ID="$2"
      shift 2
      ;;
    --parallelism)
      require_value "$1" "${2:-}"
      PARALLELISM="$2"
      shift 2
      ;;
    --shared-results-root)
      require_value "$1" "${2:-}"
      SHARED_RESULTS_ROOT="$2"
      shift 2
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
      die "unknown option: $1"
      ;;
  esac
done

[[ -n "${ASSIGNMENTS_FILE}" ]] || die "--assignments is required"

require_command awk
require_command bash
require_command base64
require_command date
require_command timeout
require_file "${ROOT_PREFLIGHT_SCRIPT}"
require_file "${ROOT_DIR}/scripts/run_docker_fuzz_single.sh"

BATCH_ID="$(sanitize_token "${BATCH_ID}")"
[[ -n "${BATCH_ID}" ]] || die "batch id resolved to an empty token"
[[ "${PARALLELISM}" =~ ^[1-9][0-9]*$ ]] || die "--parallelism must be a positive integer"

load_machine_list "${MACHINE_LIST_FILE}"
load_assignments "${ASSIGNMENTS_FILE}" "$(machine_count)" "${BATCH_ID}"

print_plan_row() {
  local index="$1"
  local machine_line="${ASSIGNMENT_MACHINE_LINES[$index]}"
  local project="${ASSIGNMENT_PROJECTS[$index]}"
  local mode="${ASSIGNMENT_MODES[$index]}"
  local run_hours="${ASSIGNMENT_RUN_HOURS[$index]}"
  local label="${ASSIGNMENT_LABELS[$index]}"
  local assignment_id="${ASSIGNMENT_IDS[$index]}"
  local tracking_mode="${ASSIGNMENT_TRACKING_MODES[$index]}"
  local use_backed="${ASSIGNMENT_USE_BACKED_VALUES[$index]}"
  local ssh_target="${MACHINE_COMMANDS[$machine_line]}"
  local assignment_root="${DEFAULT_REMOTE_RUNS_ROOT}/${assignment_id}"
  local shared_assignment_root="${SHARED_RESULTS_ROOT}/${assignment_id}"

  printf 'assignment_id=%s\n' "${assignment_id}"
  printf '  machine_line=%s\n' "${machine_line}"
  printf '  ssh_target=%s\n' "${ssh_target}"
  printf '  project=%s\n' "${project}"
  printf '  mode=%s\n' "${mode}"
  printf '  unit_test_enabled=true\n'
  printf '  tracking_mode=%s\n' "${tracking_mode}"
  printf '  use_backed=%s\n' "${use_backed}"
  printf '  run_hours=%s\n' "${run_hours}"
  printf '  label=%s\n' "${label:-<empty>}"
  printf '  remote_assignment_root=%s\n' "${assignment_root}"
  printf '  remote_shared_assignment_root=%s\n' "${shared_assignment_root}"
}

log_info "validated $(assignment_count) assignments against $(machine_count) machine entries"

if [[ "${DRY_RUN}" == "true" ]]; then
  local_index="0"
  while (( local_index < $(assignment_count) )); do
    print_plan_row "${local_index}"
    local_index="$(( local_index + 1 ))"
  done
  printf 'batch_id=%s\n' "${BATCH_ID}"
  exit 0
fi

mkdir -p "${DEFAULT_LAUNCH_LOG_DIR}/${BATCH_ID}"

LOCAL_RUNNER_SCRIPT_B64="$(base64 < "${ROOT_DIR}/scripts/run_docker_fuzz_single.sh" | tr -d '\n')"
[[ -n "${LOCAL_RUNNER_SCRIPT_B64}" ]] || die "failed to encode local scripts/run_docker_fuzz_single.sh"

PLAN_FILE="${DEFAULT_LAUNCH_LOG_DIR}/${BATCH_ID}/plan.tsv"
{
  printf 'assignment_id\tmachine_line\tproject\tmode\trun_hours\ttracking_mode\tuse_backed\tssh_target\tassignment_root\tshared_assignment_root\n'
} > "${PLAN_FILE}"

launch_failed="false"
launch_one_assignment() {
  local local_index="$1"
  local machine_line="${ASSIGNMENT_MACHINE_LINES[$local_index]}"
  local project="${ASSIGNMENT_PROJECTS[$local_index]}"
  local mode="${ASSIGNMENT_MODES[$local_index]}"
  local run_hours="${ASSIGNMENT_RUN_HOURS[$local_index]}"
  local label="${ASSIGNMENT_LABELS[$local_index]}"
  local assignment_id="${ASSIGNMENT_IDS[$local_index]}"
  local tracking_mode="${ASSIGNMENT_TRACKING_MODES[$local_index]}"
  local use_backed="${ASSIGNMENT_USE_BACKED_VALUES[$local_index]}"
  local ssh_target="${MACHINE_COMMANDS[$machine_line]}"
  local assignment_root="${DEFAULT_REMOTE_RUNS_ROOT}/${assignment_id}"
  local shared_assignment_root="${SHARED_RESULTS_ROOT}/${assignment_id}"
  local log_file="${DEFAULT_LAUNCH_LOG_DIR}/${BATCH_ID}/${assignment_id}.log"
  local remote_args=()

  {
    log_info "launching ${assignment_id} on machine_line=${machine_line} project=${project} mode=${mode}"
    if ! ssh_stream_local_script_with_timeout 20 "${ssh_target}" "${ROOT_PREFLIGHT_SCRIPT}"; then
      log_error "root access preflight failed for ${assignment_id}; expected direct root or passwordless sudo"
      return 1
    fi

    remote_args=(
      --assignment-id "${assignment_id}"
      --machine-line "${machine_line}"
      --ssh-target-display-b64 "$(printf '%s' "${ssh_target}" | base64 | tr -d '\n')"
      --project "${project}"
      --mode "${mode}"
      --run-hours "${run_hours}"
      --tracking-mode "${tracking_mode}"
      --use-backed "${use_backed}"
      --shared-results-root "${SHARED_RESULTS_ROOT}"
      --runner-script-b64 "${LOCAL_RUNNER_SCRIPT_B64}"
    )
    if [[ -n "${label}" ]]; then
      remote_args+=(--label-b64 "$(printf '%s' "${label}" | base64 | tr -d '\n')")
    fi

    if ssh_stream_local_script \
      "${ssh_target}" \
      "${REMOTE_BOOTSTRAP_SCRIPT}" \
      "${remote_args[@]}"; then
      log_info "launched ${assignment_id}; controller log=${log_file}"
      return 0
    fi

    log_error "launch failed for ${assignment_id}; controller log=${log_file}"
    return 1
  } > >(tee "${log_file}") 2>&1
}

local_index="0"
while (( local_index < $(assignment_count) )); do
  machine_line="${ASSIGNMENT_MACHINE_LINES[$local_index]}"
  project="${ASSIGNMENT_PROJECTS[$local_index]}"
  mode="${ASSIGNMENT_MODES[$local_index]}"
  run_hours="${ASSIGNMENT_RUN_HOURS[$local_index]}"
  assignment_id="${ASSIGNMENT_IDS[$local_index]}"
  tracking_mode="${ASSIGNMENT_TRACKING_MODES[$local_index]}"
  use_backed="${ASSIGNMENT_USE_BACKED_VALUES[$local_index]}"
  ssh_target="${MACHINE_COMMANDS[$machine_line]}"
  assignment_root="${DEFAULT_REMOTE_RUNS_ROOT}/${assignment_id}"
  shared_assignment_root="${SHARED_RESULTS_ROOT}/${assignment_id}"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${assignment_id}" \
    "${machine_line}" \
    "${project}" \
    "${mode}" \
    "${run_hours}" \
    "${tracking_mode}" \
    "${use_backed}" \
    "${ssh_target}" \
    "${assignment_root}" \
    "${shared_assignment_root}" >> "${PLAN_FILE}"
  local_index="$(( local_index + 1 ))"
done

running_jobs="0"
local_index="0"
while (( local_index < $(assignment_count) )); do
  while (( running_jobs >= PARALLELISM )); do
    if ! wait -n; then
      launch_failed="true"
    fi
    running_jobs="$(( running_jobs - 1 ))"
  done

  launch_one_assignment "${local_index}" &
  running_jobs="$(( running_jobs + 1 ))"
  local_index="$(( local_index + 1 ))"
done

while (( running_jobs > 0 )); do
  if ! wait -n; then
    launch_failed="true"
  fi
  running_jobs="$(( running_jobs - 1 ))"
done

printf 'batch_id=%s\n' "${BATCH_ID}"
printf 'launch_plan=%s\n' "${PLAN_FILE}"

if [[ "${launch_failed}" == "true" ]]; then
  exit 1
fi
