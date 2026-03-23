#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${ECFUZZ_AZURE_EXP_LIB_LOADED:-}" ]]; then
  return 0
fi
readonly ECFUZZ_AZURE_EXP_LIB_LOADED=1

AZURE_EXP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${AZURE_EXP_DIR}/.." && pwd)"
REMOTE_BOOTSTRAP_SCRIPT="${AZURE_EXP_DIR}/remote_bootstrap_and_run.sh"

DEFAULT_MACHINE_LIST_FILE="${AZURE_EXP_DIR}/machine_list.txt"
DEFAULT_COLLECTED_DIR="${AZURE_EXP_DIR}/collected"
DEFAULT_LAUNCH_LOG_DIR="${AZURE_EXP_DIR}/launch_logs"
DEFAULT_MONITOR_INTERVAL_SECONDS="60"
DEFAULT_MONITOR_SSH_TIMEOUT_SECONDS="20"

DEFAULT_GIT_URL="https://github.com/shuaiwang516/ECFuzz.git"
DEFAULT_REMOTE_BASE_DIR="/users/swang516"
DEFAULT_REMOTE_DOCKER_DATA_ROOT="${DEFAULT_REMOTE_BASE_DIR}/docker"
DEFAULT_REMOTE_REPO_PATH="${DEFAULT_REMOTE_BASE_DIR}/ECFuzz"
DEFAULT_REMOTE_EXPERIMENT_ROOT="${DEFAULT_REMOTE_BASE_DIR}/azure_exp"
DEFAULT_REMOTE_RUNS_ROOT="${DEFAULT_REMOTE_EXPERIMENT_ROOT}/runs"
DEFAULT_REMOTE_SHARED_RESULTS_ROOT="/proj/uptesting/ecfuzz-shared-results"
DEFAULT_TMUX_SESSION="ecfuzzExp"

SUPPORTED_PROJECTS=(hadoop-common hadoop-hdfs hbase zookeeper alluxio)
SUPPORTED_MODES=(ECFuzz ECFuzzParamTracking)

declare -ag MACHINE_COMMANDS=()
declare -ag ASSIGNMENT_MACHINE_LINES=()
declare -ag ASSIGNMENT_PROJECTS=()
declare -ag ASSIGNMENT_MODES=()
declare -ag ASSIGNMENT_RUN_HOURS=()
declare -ag ASSIGNMENT_LABELS=()
declare -ag ASSIGNMENT_IDS=()
declare -ag ASSIGNMENT_TRACKING_MODES=()
declare -ag ASSIGNMENT_USE_BACKED_VALUES=()

timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_info() {
  printf '[%s] %s\n' "$(timestamp_utc)" "$*"
}

log_warn() {
  printf '[%s] WARN: %s\n' "$(timestamp_utc)" "$*" >&2
}

log_error() {
  printf '[%s] ERROR: %s\n' "$(timestamp_utc)" "$*" >&2
}

die() {
  log_error "$*"
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || die "file not found: ${path}"
}

require_dir() {
  local path="$1"
  [[ -d "${path}" ]] || die "directory not found: ${path}"
}

require_command() {
  local command_name="$1"
  command -v "${command_name}" >/dev/null 2>&1 || die "required command not found: ${command_name}"
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  [[ -n "${value}" ]] || die "missing value for ${flag}"
}

trim_whitespace() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

sanitize_token() {
  local value="$1"
  value="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-')"
  value="${value#-}"
  value="${value%-}"
  printf '%s' "${value}"
}

expected_assignment_count() {
  printf '%s\n' "$(( ${#SUPPORTED_PROJECTS[@]} * ${#SUPPORTED_MODES[@]} ))"
}

machine_count() {
  printf '%s\n' "$(( ${#MACHINE_COMMANDS[@]} - 1 ))"
}

assignment_count() {
  printf '%s\n' "${#ASSIGNMENT_IDS[@]}"
}

is_valid_project() {
  local candidate="$1"
  local project
  for project in "${SUPPORTED_PROJECTS[@]}"; do
    if [[ "${project}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

is_valid_mode() {
  local candidate="$1"
  local mode
  for mode in "${SUPPORTED_MODES[@]}"; do
    if [[ "${mode}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

mode_to_tracking_mode() {
  local mode="$1"
  case "${mode}" in
    ECFuzz)
      printf '%s\n' "off"
      ;;
    ECFuzzParamTracking)
      printf '%s\n' "on"
      ;;
    *)
      die "invalid mode: ${mode}"
      ;;
  esac
}

mode_to_use_backed() {
  local mode="$1"
  case "${mode}" in
    ECFuzz)
      printf '%s\n' "off"
      ;;
    ECFuzzParamTracking)
      printf '%s\n' "on"
      ;;
    *)
      die "invalid mode: ${mode}"
      ;;
  esac
}

mode_to_slug() {
  local mode="$1"
  case "${mode}" in
    ECFuzz)
      printf '%s\n' "ecfuzz"
      ;;
    ECFuzzParamTracking)
      printf '%s\n' "ecfuzz-paramtracking"
      ;;
    *)
      die "invalid mode: ${mode}"
      ;;
  esac
}

build_assignment_id() {
  local batch_id="$1"
  local machine_line="$2"
  local project="$3"
  local mode="$4"
  local safe_batch_id
  safe_batch_id="$(sanitize_token "${batch_id}")"
  [[ -n "${safe_batch_id}" ]] || die "batch id resolved to an empty token"
  printf '%s\n' "${safe_batch_id}-m$(printf '%02d' "${machine_line}")-$(sanitize_token "${project}")-$(mode_to_slug "${mode}")"
}

build_remote_bash_lc_string() {
  local remote_script="$1"
  local quoted=""
  printf -v quoted '%q ' sudo -n bash -lc "${remote_script}"
  printf '%s' "${quoted% }"
}

build_remote_bash_stdin_string() {
  local quoted=""
  printf -v quoted '%q ' sudo -n bash -s -- "$@"
  printf '%s' "${quoted% }"
}

ssh_run_remote_bash() {
  local ssh_command="$1"
  local remote_script="$2"
  local remote_invocation
  remote_invocation="$(build_remote_bash_lc_string "${remote_script}")"
  bash -lc "${ssh_command} ${remote_invocation}"
}

ssh_run_remote_bash_with_timeout() {
  local timeout_seconds="$1"
  local ssh_command="$2"
  local remote_script="$3"
  local remote_invocation
  remote_invocation="$(build_remote_bash_lc_string "${remote_script}")"
  timeout "${timeout_seconds}s" bash -lc "${ssh_command} ${remote_invocation}"
}

ssh_stream_local_script() {
  local ssh_command="$1"
  local local_script_path="$2"
  shift 2
  local remote_invocation
  remote_invocation="$(build_remote_bash_stdin_string "$@")"
  bash -lc "${ssh_command} ${remote_invocation}" < "${local_script_path}"
}

ssh_stream_local_script_with_timeout() {
  local timeout_seconds="$1"
  local ssh_command="$2"
  local local_script_path="$3"
  shift 3
  local remote_invocation
  remote_invocation="$(build_remote_bash_stdin_string "$@")"
  timeout "${timeout_seconds}s" bash -lc "${ssh_command} ${remote_invocation}" < "${local_script_path}"
}

validate_machine_command() {
  local machine_command="$1"
  [[ "${machine_command}" =~ ^ssh([[:space:]]+.+)$ ]] || return 1
  case "${machine_command}" in
    *$'\n'*|*$'\r'*)
      return 1
      ;;
  esac
  return 0
}

normalize_machine_command() {
  local machine_command="$1"
  if [[ "${machine_command}" =~ ^ssh[[:space:]]+([^[:space:]-][^[:space:]]*)[[:space:]]+-p[[:space:]]+([0-9]+)$ ]]; then
    printf 'ssh -p %s %s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[1]}"
    return 0
  fi
  printf '%s\n' "${machine_command}"
}

load_machine_list() {
  local machine_list_file="$1"
  require_file "${machine_list_file}"

  MACHINE_COMMANDS=("")

  local line_number="0"
  local raw_line=""
  local machine_command=""
  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    line_number="$(( line_number + 1 ))"
    raw_line="${raw_line%$'\r'}"
    machine_command="$(trim_whitespace "${raw_line}")"

    if [[ -z "${machine_command}" ]]; then
      die "${machine_list_file}: line ${line_number}: blank lines are not allowed because assignment references use physical 1-based line numbers"
    fi

    if ! validate_machine_command "${machine_command}"; then
      die "${machine_list_file}: line ${line_number}: invalid machine entry '${machine_command}'"
    fi

    machine_command="$(normalize_machine_command "${machine_command}")"
    MACHINE_COMMANDS+=("${machine_command}")
  done < "${machine_list_file}"

  if (( $(machine_count) == 0 )); then
    die "${machine_list_file}: no machine entries found"
  fi
}

normalize_assignments_tsv() {
  local assignments_file="$1"
  awk -F '\t' '
    BEGIN {
      OFS = "\t"
      has_label = 0
    }
    {
      sub(/\r$/, "", $NF)
    }
    NR == 1 {
      if (NF != 4 && NF != 5) {
        printf "%s:%d: expected header columns machine_line, project, mode, run_hours[, label]\n", FILENAME, NR > "/dev/stderr"
        exit 1
      }
      if ($1 != "machine_line" || $2 != "project" || $3 != "mode" || $4 != "run_hours") {
        printf "%s:%d: invalid header; expected machine_line, project, mode, run_hours[, label]\n", FILENAME, NR > "/dev/stderr"
        exit 1
      }
      if (NF == 5) {
        if ($5 != "label") {
          printf "%s:%d: invalid fifth header column; expected label\n", FILENAME, NR > "/dev/stderr"
          exit 1
        }
        has_label = 1
      }
      next
    }
    {
      if ((has_label && NF != 5) || (!has_label && NF != 4)) {
        printf "%s:%d: expected %d tab-separated columns, found %d\n", FILENAME, NR, has_label ? 5 : 4, NF > "/dev/stderr"
        exit 1
      }
      if (has_label) {
        print $1, $2, $3, $4, $5
      } else {
        print $1, $2, $3, $4, ""
      }
    }
  ' "${assignments_file}"
}

load_assignments() {
  local assignments_file="$1"
  local available_machine_count="$2"
  local batch_id="$3"

  require_file "${assignments_file}"

  ASSIGNMENT_MACHINE_LINES=()
  ASSIGNMENT_PROJECTS=()
  ASSIGNMENT_MODES=()
  ASSIGNMENT_RUN_HOURS=()
  ASSIGNMENT_LABELS=()
  ASSIGNMENT_IDS=()
  ASSIGNMENT_TRACKING_MODES=()
  ASSIGNMENT_USE_BACKED_VALUES=()

  local normalized_rows
  if ! normalized_rows="$(normalize_assignments_tsv "${assignments_file}")"; then
    exit 1
  fi

  local -A seen_machine_lines=()
  local -A seen_combinations=()
  local row_index="1"
  local row_count="0"

  local machine_line=""
  local project=""
  local mode=""
  local run_hours=""
  local label=""
  if [[ -n "${normalized_rows}" ]]; then
    while IFS=$'\t' read -r machine_line project mode run_hours label; do
      row_index="$(( row_index + 1 ))"
      row_count="$(( row_count + 1 ))"

      machine_line="$(trim_whitespace "${machine_line}")"
      project="$(trim_whitespace "${project}")"
      mode="$(trim_whitespace "${mode}")"
      run_hours="$(trim_whitespace "${run_hours}")"
      label="$(trim_whitespace "${label}")"

      if ! [[ "${machine_line}" =~ ^[0-9]+$ ]]; then
        die "${assignments_file}: line ${row_index}: machine_line must be a 1-based positive integer"
      fi

      if (( machine_line < 1 || machine_line > available_machine_count )); then
        die "${assignments_file}: line ${row_index}: machine_line ${machine_line} is out of range for ${available_machine_count} machine entries"
      fi

      if ! is_valid_project "${project}"; then
        die "${assignments_file}: line ${row_index}: invalid project '${project}'"
      fi

      if ! is_valid_mode "${mode}"; then
        die "${assignments_file}: line ${row_index}: invalid mode '${mode}'"
      fi

      if ! [[ "${run_hours}" =~ ^[0-9]+$ ]]; then
        die "${assignments_file}: line ${row_index}: run_hours must be a non-negative integer"
      fi

      if [[ -n "${seen_machine_lines[${machine_line}]:-}" ]]; then
        die "${assignments_file}: line ${row_index}: machine_line ${machine_line} is assigned more than once"
      fi
      seen_machine_lines["${machine_line}"]="1"

      local combination_key="${project}|${mode}"
      if [[ -n "${seen_combinations[${combination_key}]:-}" ]]; then
        die "${assignments_file}: line ${row_index}: duplicate assignment for (${project}, ${mode})"
      fi
      seen_combinations["${combination_key}"]="1"

      ASSIGNMENT_MACHINE_LINES+=("${machine_line}")
      ASSIGNMENT_PROJECTS+=("${project}")
      ASSIGNMENT_MODES+=("${mode}")
      ASSIGNMENT_RUN_HOURS+=("${run_hours}")
      ASSIGNMENT_LABELS+=("${label}")
      ASSIGNMENT_IDS+=("$(build_assignment_id "${batch_id}" "${machine_line}" "${project}" "${mode}")")
      ASSIGNMENT_TRACKING_MODES+=("$(mode_to_tracking_mode "${mode}")")
      ASSIGNMENT_USE_BACKED_VALUES+=("$(mode_to_use_backed "${mode}")")
    done <<< "${normalized_rows}"
  fi

  local expected_count
  expected_count="$(expected_assignment_count)"
  if (( row_count != expected_count )); then
    die "${assignments_file}: expected ${expected_count} assignments, found ${row_count}"
  fi

  local expected_project=""
  local expected_mode=""
  for expected_project in "${SUPPORTED_PROJECTS[@]}"; do
    for expected_mode in "${SUPPORTED_MODES[@]}"; do
      if [[ -z "${seen_combinations[${expected_project}|${expected_mode}]:-}" ]]; then
        die "${assignments_file}: missing assignment for (${expected_project}, ${expected_mode})"
      fi
    done
  done
}
