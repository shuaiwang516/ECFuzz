#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

print_usage() {
  cat <<EOF
Usage:
  monitor_azure_batch.sh --assignments <file> --batch-id <id> [options]

Required:
  --assignments <file>            Same TSV used for launch
  --batch-id <id>                 Same batch id used for launch

Options:
  --machine-list <file>           Inventory file. Default: ${DEFAULT_MACHINE_LIST_FILE}
  --collected-root <dir>          Local collection root. Default: ${DEFAULT_COLLECTED_DIR}
  --shared-results-root <path>    Remote shared results root. Default: ${DEFAULT_REMOTE_SHARED_RESULTS_ROOT}
  --interval-seconds <int>        Poll interval for live monitoring. Default: ${DEFAULT_MONITOR_INTERVAL_SECONDS}
  --ssh-timeout-seconds <int>     Per-machine SSH timeout for monitor probes. Default: ${DEFAULT_MONITOR_SSH_TIMEOUT_SECONDS}
  --once                          Run one monitoring pass and exit
  --dry-run                       Validate config and print the resolved monitor plan without SSH
  --help                          Show this help

Behavior:
  - Prints high-signal per-assignment status each pass
  - Pulls manifests and logs back under azure_exp/collected/<batch-id>/<assignment_id>/
  - Falls back to the shared results root if machine-local run data is gone
  - Uses tar-over-SSH so full SSH command lines from machine_list.txt remain usable
EOF
}

MACHINE_LIST_FILE="${DEFAULT_MACHINE_LIST_FILE}"
ASSIGNMENTS_FILE=""
BATCH_ID=""
COLLECTED_ROOT="${DEFAULT_COLLECTED_DIR}"
SHARED_RESULTS_ROOT="${DEFAULT_REMOTE_SHARED_RESULTS_ROOT}"
INTERVAL_SECONDS="${DEFAULT_MONITOR_INTERVAL_SECONDS}"
SSH_TIMEOUT_SECONDS="${DEFAULT_MONITOR_SSH_TIMEOUT_SECONDS}"
RUN_ONCE="false"
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
    --collected-root)
      require_value "$1" "${2:-}"
      COLLECTED_ROOT="$2"
      shift 2
      ;;
    --shared-results-root)
      require_value "$1" "${2:-}"
      SHARED_RESULTS_ROOT="$2"
      shift 2
      ;;
    --interval-seconds)
      require_value "$1" "${2:-}"
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --ssh-timeout-seconds)
      require_value "$1" "${2:-}"
      SSH_TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --once)
      RUN_ONCE="true"
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
      die "unknown option: $1"
      ;;
  esac
done

[[ -n "${ASSIGNMENTS_FILE}" ]] || die "--assignments is required"
[[ -n "${BATCH_ID}" ]] || die "--batch-id is required"

require_command awk
require_command bash
require_command date
require_command tar
require_command timeout
require_command mktemp

BATCH_ID="$(sanitize_token "${BATCH_ID}")"
[[ -n "${BATCH_ID}" ]] || die "batch id resolved to an empty token"
[[ "${INTERVAL_SECONDS}" =~ ^[0-9]+$ ]] || die "--interval-seconds must be a non-negative integer"
[[ "${SSH_TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || die "--ssh-timeout-seconds must be a non-negative integer"

load_machine_list "${MACHINE_LIST_FILE}"
load_assignments "${ASSIGNMENTS_FILE}" "$(machine_count)" "${BATCH_ID}"

print_monitor_plan_row() {
  local index="$1"
  local machine_line="${ASSIGNMENT_MACHINE_LINES[$index]}"
  local project="${ASSIGNMENT_PROJECTS[$index]}"
  local mode="${ASSIGNMENT_MODES[$index]}"
  local assignment_id="${ASSIGNMENT_IDS[$index]}"
  local ssh_target="${MACHINE_COMMANDS[$machine_line]}"
  local assignment_root="${DEFAULT_REMOTE_RUNS_ROOT}/${assignment_id}"
  local shared_assignment_root="${SHARED_RESULTS_ROOT}/${assignment_id}"
  local collect_dir="${COLLECTED_ROOT}/${BATCH_ID}/${assignment_id}"
  printf 'assignment_id=%s\n' "${assignment_id}"
  printf '  machine_line=%s\n' "${machine_line}"
  printf '  ssh_target=%s\n' "${ssh_target}"
  printf '  project=%s\n' "${project}"
  printf '  mode=%s\n' "${mode}"
  printf '  remote_assignment_root=%s\n' "${assignment_root}"
  printf '  remote_shared_assignment_root=%s\n' "${shared_assignment_root}"
  printf '  local_collect_dir=%s\n' "${collect_dir}"
}

if [[ "${DRY_RUN}" == "true" ]]; then
  local_index="0"
  while (( local_index < $(assignment_count) )); do
    print_monitor_plan_row "${local_index}"
    local_index="$(( local_index + 1 ))"
  done
  exit 0
fi

mkdir -p "${COLLECTED_ROOT}/${BATCH_ID}"

monitor_one_assignment() {
  local index="$1"
  local machine_line="${ASSIGNMENT_MACHINE_LINES[$index]}"
  local project="${ASSIGNMENT_PROJECTS[$index]}"
  local mode="${ASSIGNMENT_MODES[$index]}"
  local assignment_id="${ASSIGNMENT_IDS[$index]}"
  local ssh_target="${MACHINE_COMMANDS[$machine_line]}"
  local assignment_root="${DEFAULT_REMOTE_RUNS_ROOT}/${assignment_id}"
  local shared_assignment_root="${SHARED_RESULTS_ROOT}/${assignment_id}"
  local collect_dir="${COLLECTED_ROOT}/${BATCH_ID}/${assignment_id}"
  local status_output=""
  local remote_status_script=""
  local remote_status_script_file=""

  remote_status_script=$(cat <<EOF
set -euo pipefail
assignment_root=$(printf '%q' "${assignment_root}")
shared_assignment_root=$(printf '%q' "${shared_assignment_root}")
tmux_session=$(printf '%q' "${DEFAULT_TMUX_SESSION}")

state_root="\${assignment_root}"
if [[ ! -d "\${state_root}" && -d "\${shared_assignment_root}" ]]; then
  state_root="\${shared_assignment_root}"
fi

phase="not_started"
tmux_state="absent"
image_tag=""
case_root=""
runner_exit_code=""
shared_copy_state=""

if [[ -f "\${state_root}/status/phase.txt" ]]; then
  phase=\$(tr -d '\r\n' < "\${state_root}/status/phase.txt")
fi

if tmux has-session -t "\${tmux_session}" >/dev/null 2>&1; then
  tmux_state="present"
fi

if [[ -f "\${state_root}/status/runner_exit_code.txt" ]]; then
  runner_exit_code=\$(tr -d '\r\n' < "\${state_root}/status/runner_exit_code.txt")
fi

if [[ -f "\${state_root}/assignment_manifest.txt" ]]; then
  image_tag=\$(awk -F= '/^image_tag=/{print substr(\$0, index(\$0, "=") + 1)}' "\${state_root}/assignment_manifest.txt" | tail -n 1)
fi

if [[ -f "\${state_root}/status/latest_case_root.txt" ]]; then
  case_root=\$(tr -d '\r\n' < "\${state_root}/status/latest_case_root.txt")
fi

if [[ -f "\${state_root}/status/shared_copy_state.txt" ]]; then
  shared_copy_state=\$(tr -d '\r\n' < "\${state_root}/status/shared_copy_state.txt")
fi

if [[ -n "\${case_root}" && ( ! -d "\${case_root}" || "\${case_root#\${state_root}/}" == "\${case_root}" ) ]]; then
  case_root=""
fi

if [[ -z "\${case_root}" ]]; then
  for candidate in "\${state_root}"/20*; do
    [[ -d "\${candidate}" && -f "\${candidate}/manifest.txt" ]] || continue
    case_root="\${candidate}"
  done
fi

state="not_started"
if [[ "\${phase}" == "completed" ]]; then
  state="completed"
elif [[ "\${phase}" == "shared_copy" ]]; then
  state="publishing"
elif [[ "\${phase}" == "shared_copy_failed" || "\${phase}" == "runner_failed" || "\${phase}" == failed:* ]]; then
  state="failed"
elif [[ "\${tmux_state}" == "present" ]]; then
  state="running"
elif [[ "\${phase}" != "not_started" ]]; then
  state="launching"
fi

fuzzer_tail=""
if [[ -n "\${case_root}" && -f "\${case_root}/logs/fuzzer.log" ]]; then
  fuzzer_tail=\$(tail -n 3 "\${case_root}/logs/fuzzer.log" | tr '\n' '\v')
fi

printf 'phase=%s\n' "\${phase}"
printf 'tmux_state=%s\n' "\${tmux_state}"
printf 'state=%s\n' "\${state}"
printf 'image_tag=%s\n' "\${image_tag}"
printf 'case_root=%s\n' "\${case_root}"
printf 'runner_exit_code=%s\n' "\${runner_exit_code}"
printf 'shared_copy_state=%s\n' "\${shared_copy_state}"
printf 'state_root=%s\n' "\${state_root}"
printf 'fuzzer_tail=%s\n' "\${fuzzer_tail}"
EOF
)

  remote_status_script_file="$(mktemp)"
  printf '%s\n' "${remote_status_script}" > "${remote_status_script_file}"

  if ! status_output="$(ssh_stream_local_script_with_timeout "${SSH_TIMEOUT_SECONDS}" "${ssh_target}" "${remote_status_script_file}" 2>/dev/null)"; then
    rm -f "${remote_status_script_file}"
    printf '[m%02d %s %s] ssh=down state=unreachable assignment_root=%s\n' "${machine_line}" "${project}" "${mode}" "${assignment_root}"
    return 0
  fi
  rm -f "${remote_status_script_file}"

  local phase=""
  local tmux_state=""
  local state=""
  local image_tag=""
  local case_root=""
  local runner_exit_code=""
  local shared_copy_state=""
  local state_root=""
  local fuzzer_tail=""
  while IFS='=' read -r key value; do
    case "${key}" in
      phase) phase="${value}" ;;
      tmux_state) tmux_state="${value}" ;;
      state) state="${value}" ;;
      image_tag) image_tag="${value}" ;;
      case_root) case_root="${value}" ;;
      runner_exit_code) runner_exit_code="${value}" ;;
      shared_copy_state) shared_copy_state="${value}" ;;
      state_root) state_root="${value}" ;;
      fuzzer_tail) fuzzer_tail="${value}" ;;
    esac
  done <<< "${status_output}"

  mkdir -p "${collect_dir}"

  local remote_fetch_script=""
  local remote_fetch_script_file=""
  remote_fetch_script=$(cat <<EOF
set -euo pipefail
assignment_root=$(printf '%q' "${assignment_root}")
shared_assignment_root=$(printf '%q' "${shared_assignment_root}")
state_root="\${assignment_root}"
if [[ ! -d "\${state_root}" && -d "\${shared_assignment_root}" ]]; then
  state_root="\${shared_assignment_root}"
fi
case_root=""
if [[ -f "\${state_root}/status/latest_case_root.txt" ]]; then
  case_root=\$(tr -d '\r\n' < "\${state_root}/status/latest_case_root.txt")
fi
if [[ -n "\${case_root}" && ( ! -d "\${case_root}" || "\${case_root#\${state_root}/}" == "\${case_root}" ) ]]; then
  case_root=""
fi
if [[ -z "\${case_root}" ]]; then
  for candidate in "\${state_root}"/20*; do
    [[ -d "\${candidate}" && -f "\${candidate}/manifest.txt" ]] || continue
    case_root="\${candidate}"
  done
fi

if [[ ! -d "\${state_root}" ]]; then
  exit 0
fi

cd "\${state_root}"
items=()
add_item() {
  local path="\$1"
  [[ -e "\${path}" ]] || return 0
  items+=("\${path}")
}

add_item "assignment_manifest.txt"
if [[ -d status ]]; then
  while IFS= read -r status_file; do
    items+=("\${status_file}")
  done < <(find status -maxdepth 1 -type f | LC_ALL=C sort)
fi

if [[ -n "\${case_root}" ]]; then
  case_rel="\${case_root#\${state_root}/}"
  add_item "\${case_rel}/manifest.txt"
  add_item "\${case_rel}/logs/prepare.log"
  add_item "\${case_rel}/logs/fuzzer.log"
  add_item "\${case_rel}/logs/docker_command.sh"
  add_item "\${case_rel}/logs/internal_fuzzer.log"
  add_item "\${case_rel}/comparison_metrics/summary.tsv"
  add_item "\${case_rel}/param_tracking/summary.tsv"
fi

if (( \${#items[@]} == 0 )); then
  exit 0
fi

tar -cf - "\${items[@]}"
EOF
)

  local tar_tmp=""
  tar_tmp="$(mktemp)"
  remote_fetch_script_file="$(mktemp)"
  printf '%s\n' "${remote_fetch_script}" > "${remote_fetch_script_file}"
  if ssh_stream_local_script_with_timeout "${SSH_TIMEOUT_SECONDS}" "${ssh_target}" "${remote_fetch_script_file}" > "${tar_tmp}" 2>/dev/null; then
    if [[ -s "${tar_tmp}" ]]; then
      if tar -tf "${tar_tmp}" >/dev/null 2>&1; then
        tar -xf "${tar_tmp}" -C "${collect_dir}"
      else
        cp "${tar_tmp}" "${collect_dir}/fetch_error.txt"
      fi
    fi
  else
    printf 'remote fetch failed\n' > "${collect_dir}/fetch_error.txt"
  fi
  rm -f "${remote_fetch_script_file}"
  rm -f "${tar_tmp}"

  printf '[m%02d %s %s] ssh=up tmux=%s state=%s phase=%s image=%s assignment_root=%s state_root=%s case_root=%s rc=%s shared=%s\n' \
    "${machine_line}" \
    "${project}" \
    "${mode}" \
    "${tmux_state:-unknown}" \
    "${state:-unknown}" \
    "${phase:-unknown}" \
    "${image_tag:-<unknown>}" \
    "${assignment_root}" \
    "${state_root:-<unknown>}" \
    "${case_root:-<unknown>}" \
    "${runner_exit_code:-<none>}" \
    "${shared_copy_state:-<unknown>}"

  if [[ -n "${fuzzer_tail}" ]]; then
    printf '  tail: %s\n' "${fuzzer_tail//$'\v'/ | }"
  fi
  printf '  collected: %s\n' "${collect_dir}"
}

trap 'printf "\n"; exit 0' INT TERM

while true; do
  printf '=== %s batch=%s ===\n' "$(timestamp_utc)" "${BATCH_ID}"
  local_index="0"
  while (( local_index < $(assignment_count) )); do
    monitor_one_assignment "${local_index}"
    local_index="$(( local_index + 1 ))"
  done

  if [[ "${RUN_ONCE}" == "true" ]]; then
    exit 0
  fi
  sleep "${INTERVAL_SECONDS}"
done
