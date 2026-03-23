#!/usr/bin/env bash
set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage:
  remote_bootstrap_and_run.sh --assignment-id <id> --machine-line <n> (--ssh-target-display <text> | --ssh-target-display-b64 <text>) --project <name> --mode <name> --run-hours <int> --tracking-mode <on|off> --use-backed <on|off> [options]

Required:
  --assignment-id <id>
  --machine-line <n>
  --ssh-target-display <text>
  --ssh-target-display-b64 <text>
  --project <name>
  --mode <ECFuzz|ECFuzzParamTracking>
  --run-hours <int>
  --tracking-mode <on|off>
  --use-backed <on|off>

Options:
  --label <text>                  Optional label recorded in manifests and forwarded to the runner
  --label-b64 <text>              Base64-encoded form of --label for SSH-safe transport
  --runner-script-b64 <text>      Base64-encoded controller copy of scripts/run_docker_fuzz_single.sh
  --git-url <url>                 Default: https://github.com/shuaiwang516/ECFuzz.git
  --docker-data-root <path>       Default: /users/swang516/docker
  --repo-path <path>              Default: /users/swang516/ECFuzz
  --experiment-root <path>        Default: /users/swang516/azure_exp
  --shared-results-root <path>    Default: /proj/uptesting/ecfuzz-shared-results
  --tmux-session <name>           Must be ecfuzzExp if supplied
  --dry-run                       Print the resolved remote plan and exit
  --help                          Show this help
EOF
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  [[ -n "${value}" ]] || {
    echo "missing value for ${flag}" >&2
    exit 1
  }
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

timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf '[%s] %s\n' "$(timestamp_utc)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

validate_project() {
  local project="$1"
  case "${project}" in
    hadoop-common|hadoop-hdfs|hbase|zookeeper|alluxio)
      ;;
    *)
      die "invalid project: ${project}"
      ;;
  esac
}

validate_mode() {
  local mode="$1"
  case "${mode}" in
    ECFuzz|ECFuzzParamTracking)
      ;;
    *)
      die "invalid mode: ${mode}"
      ;;
  esac
}

validate_on_off() {
  local name="$1"
  local value="$2"
  case "${value}" in
    on|off)
      ;;
    *)
      die "invalid ${name}: ${value}; expected on/off"
      ;;
  esac
}

ASSIGNMENT_ID=""
MACHINE_LINE=""
SSH_TARGET_DISPLAY=""
SSH_TARGET_DISPLAY_B64=""
PROJECT=""
MODE=""
RUN_HOURS=""
TRACKING_MODE=""
USE_BACKED=""
LABEL=""
LABEL_B64=""
RUNNER_SCRIPT_B64=""
GIT_URL="https://github.com/shuaiwang516/ECFuzz.git"
DOCKER_DATA_ROOT="/users/swang516/docker"
REPO_PATH="/users/swang516/ECFuzz"
EXPERIMENT_ROOT="/users/swang516/azure_exp"
SHARED_RESULTS_ROOT="/proj/uptesting/ecfuzz-shared-results"
TMUX_SESSION="ecfuzzExp"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --assignment-id)
      require_value "$1" "${2:-}"
      ASSIGNMENT_ID="$2"
      shift 2
      ;;
    --machine-line)
      require_value "$1" "${2:-}"
      MACHINE_LINE="$2"
      shift 2
      ;;
    --ssh-target-display)
      require_value "$1" "${2:-}"
      SSH_TARGET_DISPLAY="$2"
      shift 2
      ;;
    --ssh-target-display-b64)
      require_value "$1" "${2:-}"
      SSH_TARGET_DISPLAY_B64="$2"
      shift 2
      ;;
    --project)
      require_value "$1" "${2:-}"
      PROJECT="$2"
      shift 2
      ;;
    --mode)
      require_value "$1" "${2:-}"
      MODE="$2"
      shift 2
      ;;
    --run-hours)
      require_value "$1" "${2:-}"
      RUN_HOURS="$2"
      shift 2
      ;;
    --tracking-mode)
      require_value "$1" "${2:-}"
      TRACKING_MODE="$2"
      shift 2
      ;;
    --use-backed)
      require_value "$1" "${2:-}"
      USE_BACKED="$2"
      shift 2
      ;;
    --label)
      require_value "$1" "${2:-}"
      LABEL="$2"
      shift 2
      ;;
    --label-b64)
      require_value "$1" "${2:-}"
      LABEL_B64="$2"
      shift 2
      ;;
    --runner-script-b64)
      require_value "$1" "${2:-}"
      RUNNER_SCRIPT_B64="$2"
      shift 2
      ;;
    --git-url)
      require_value "$1" "${2:-}"
      GIT_URL="$2"
      shift 2
      ;;
    --docker-data-root)
      require_value "$1" "${2:-}"
      DOCKER_DATA_ROOT="$2"
      shift 2
      ;;
    --repo-path)
      require_value "$1" "${2:-}"
      REPO_PATH="$2"
      shift 2
      ;;
    --experiment-root)
      require_value "$1" "${2:-}"
      EXPERIMENT_ROOT="$2"
      shift 2
      ;;
    --shared-results-root)
      require_value "$1" "${2:-}"
      SHARED_RESULTS_ROOT="$2"
      shift 2
      ;;
    --tmux-session)
      require_value "$1" "${2:-}"
      TMUX_SESSION="$2"
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

ASSIGNMENT_ID="$(trim_whitespace "${ASSIGNMENT_ID}")"
PROJECT="$(trim_whitespace "${PROJECT}")"
MODE="$(trim_whitespace "${MODE}")"
RUN_HOURS="$(trim_whitespace "${RUN_HOURS}")"
TRACKING_MODE="$(trim_whitespace "${TRACKING_MODE}")"
USE_BACKED="$(trim_whitespace "${USE_BACKED}")"

if [[ -n "${SSH_TARGET_DISPLAY_B64}" ]]; then
  SSH_TARGET_DISPLAY="$(printf '%s' "${SSH_TARGET_DISPLAY_B64}" | base64 -d)"
fi
if [[ -n "${LABEL_B64}" ]]; then
  LABEL="$(printf '%s' "${LABEL_B64}" | base64 -d)"
fi
SSH_TARGET_DISPLAY="$(trim_whitespace "${SSH_TARGET_DISPLAY}")"
LABEL="$(trim_whitespace "${LABEL}")"

[[ -n "${ASSIGNMENT_ID}" ]] || die "--assignment-id is required"
[[ "${MACHINE_LINE}" =~ ^[0-9]+$ ]] || die "--machine-line must be a positive integer"
[[ -n "${SSH_TARGET_DISPLAY}" ]] || die "--ssh-target-display is required"
validate_project "${PROJECT}"
validate_mode "${MODE}"
validate_on_off "--tracking-mode" "${TRACKING_MODE}"
validate_on_off "--use-backed" "${USE_BACKED}"
[[ "${RUN_HOURS}" =~ ^[0-9]+$ ]] || die "--run-hours must be a non-negative integer"
[[ "${TMUX_SESSION}" == "ecfuzzExp" ]] || die "tmux session must be ecfuzzExp"

case "${MODE}" in
  ECFuzz)
    [[ "${TRACKING_MODE}" == "off" ]] || die "mode ECFuzz requires --tracking-mode off"
    [[ "${USE_BACKED}" == "off" ]] || die "mode ECFuzz requires --use-backed off"
    ;;
  ECFuzzParamTracking)
    [[ "${TRACKING_MODE}" == "on" ]] || die "mode ECFuzzParamTracking requires --tracking-mode on"
    [[ "${USE_BACKED}" == "on" ]] || die "mode ECFuzzParamTracking requires --use-backed on"
    ;;
esac

ASSIGNMENT_ROOT="${EXPERIMENT_ROOT}/runs/${ASSIGNMENT_ID}"
SHARED_ASSIGNMENT_ROOT="${SHARED_RESULTS_ROOT}/${ASSIGNMENT_ID}"
STATUS_DIR="${ASSIGNMENT_ROOT}/status"
PHASE_FILE="${STATUS_DIR}/phase.txt"
MANIFEST_FILE="${ASSIGNMENT_ROOT}/assignment_manifest.txt"
RUNNER_WRAPPER_SCRIPT="${ASSIGNMENT_ROOT}/tmux_runner.sh"
RUNNER_COMMAND_FILE="${STATUS_DIR}/run_command.sh"
RUNNER_LOG_FILE="${STATUS_DIR}/runner_wrapper.log"
BOOTSTRAP_FAILED_FILE="${STATUS_DIR}/bootstrap_exit_code.txt"

safe_assignment_token="$(sanitize_token "${ASSIGNMENT_ID}")"
safe_assignment_token="${safe_assignment_token:0:80}"
launch_stamp="$(date -u +%Y%m%d-%H%M%S)"
IMAGE_TAG="ecfuzz/ecfuzz-provenance-agent:exp-${safe_assignment_token}-${launch_stamp}"
RUNNER_LABEL="${ASSIGNMENT_ID}"
if [[ -n "${LABEL}" ]]; then
  RUNNER_LABEL="${ASSIGNMENT_ID}-${LABEL}"
fi

RUNNER_CMD=(
  bash scripts/run_docker_fuzz_single.sh
  --project "${PROJECT}"
  --run-hours "${RUN_HOURS}"
  --tracking-mode "${TRACKING_MODE}"
  --use-backed "${USE_BACKED}"
  --image "${IMAGE_TAG}"
  --out-root "${ASSIGNMENT_ROOT}"
  --label "${RUNNER_LABEL}"
  --skip-image-ensure
)

RUNNER_CMD_STRING=""
printf -v RUNNER_CMD_STRING '%q ' "${RUNNER_CMD[@]}"
RUNNER_CMD_STRING="${RUNNER_CMD_STRING% }"

if [[ "${DRY_RUN}" == "true" ]]; then
  printf 'assignment_id=%s\n' "${ASSIGNMENT_ID}"
  printf 'machine_line=%s\n' "${MACHINE_LINE}"
  printf 'ssh_target=%s\n' "${SSH_TARGET_DISPLAY}"
  printf 'project=%s\n' "${PROJECT}"
  printf 'mode=%s\n' "${MODE}"
  printf 'unit_test_enabled=true\n'
  printf 'tracking_mode=%s\n' "${TRACKING_MODE}"
  printf 'use_backed=%s\n' "${USE_BACKED}"
  printf 'run_hours=%s\n' "${RUN_HOURS}"
  printf 'git_url=%s\n' "${GIT_URL}"
  printf 'docker_data_root=%s\n' "${DOCKER_DATA_ROOT}"
  printf 'repo_path=%s\n' "${REPO_PATH}"
  printf 'experiment_root=%s\n' "${EXPERIMENT_ROOT}"
  printf 'assignment_root=%s\n' "${ASSIGNMENT_ROOT}"
  printf 'shared_results_root=%s\n' "${SHARED_RESULTS_ROOT}"
  printf 'shared_assignment_root=%s\n' "${SHARED_ASSIGNMENT_ROOT}"
  printf 'image_tag=%s\n' "${IMAGE_TAG}"
  printf 'tmux_session=%s\n' "${TMUX_SESSION}"
  printf 'runner_command=%s\n' "${RUNNER_CMD_STRING}"
  exit 0
fi

mkdir -p "${DOCKER_DATA_ROOT}" "$(dirname "${REPO_PATH}")" "${EXPERIMENT_ROOT}/runs"
rm -rf "${ASSIGNMENT_ROOT}"
mkdir -p "${STATUS_DIR}"
exec > >(tee -a "${STATUS_DIR}/bootstrap.log") 2>&1

current_phase="bootstrap_start"
write_phase() {
  current_phase="$1"
  printf '%s\n' "${current_phase}" > "${PHASE_FILE}"
}

write_status_file() {
  local file_path="$1"
  shift
  printf '%s\n' "$@" > "${file_path}"
}

on_exit() {
  local rc="$?"
  if [[ "${rc}" -ne 0 ]]; then
    write_status_file "${BOOTSTRAP_FAILED_FILE}" "${rc}"
    write_status_file "${STATUS_DIR}/bootstrap_failed_at.txt" "$(timestamp_utc)"
    printf 'failed:%s\n' "${current_phase}" > "${PHASE_FILE}"
  fi
}
trap on_exit EXIT

log "assignment_id=${ASSIGNMENT_ID}"
write_phase "provisioning"
write_status_file "${STATUS_DIR}/launch_requested_at.txt" "$(timestamp_utc)"

write_phase "install_packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io git tmux ca-certificates

write_phase "configure_docker"
mkdir -p /etc/docker "${DOCKER_DATA_ROOT}"
if [[ -f /etc/docker/daemon.json ]]; then
  cp -f /etc/docker/daemon.json "${STATUS_DIR}/daemon.json.before"
fi
cat > /etc/docker/daemon.json <<EOF
{
  "data-root": "${DOCKER_DATA_ROOT}"
}
EOF
systemctl enable docker
systemctl restart docker

write_phase "wait_for_docker"
docker_ready="false"
for _ in $(seq 1 20); do
  if docker info >/dev/null 2>&1; then
    docker_ready="true"
    break
  fi
  sleep 2
done
[[ "${docker_ready}" == "true" ]] || die "docker daemon did not become ready"

write_phase "clone_repo"
rm -rf "${REPO_PATH}"
git clone "${GIT_URL}" "${REPO_PATH}"

if [[ -n "${RUNNER_SCRIPT_B64}" ]]; then
  write_phase "overlay_local_runner"
  printf '%s' "${RUNNER_SCRIPT_B64}" | base64 -d > "${REPO_PATH}/scripts/run_docker_fuzz_single.sh"
  chmod +x "${REPO_PATH}/scripts/run_docker_fuzz_single.sh"
fi

write_phase "prepare_manifest"
{
  printf 'assignment_id=%s\n' "${ASSIGNMENT_ID}"
  printf 'machine_line=%s\n' "${MACHINE_LINE}"
  printf 'ssh_target=%s\n' "${SSH_TARGET_DISPLAY}"
  printf 'project=%s\n' "${PROJECT}"
  printf 'mode=%s\n' "${MODE}"
  printf 'unit_test_enabled=true\n'
  printf 'unit_test_pass_required=true\n'
  printf 'tracking_mode=%s\n' "${TRACKING_MODE}"
  printf 'use_backed=%s\n' "${USE_BACKED}"
  printf 'run_hours=%s\n' "${RUN_HOURS}"
  printf 'image_tag=%s\n' "${IMAGE_TAG}"
  printf 'local_runner_overlay=%s\n' "$( [[ -n "${RUNNER_SCRIPT_B64}" ]] && printf 'true' || printf 'false' )"
  printf 'git_url=%s\n' "${GIT_URL}"
  printf 'repo_path=%s\n' "${REPO_PATH}"
  printf 'docker_data_root=%s\n' "${DOCKER_DATA_ROOT}"
  printf 'experiment_root=%s\n' "${EXPERIMENT_ROOT}"
  printf 'assignment_root=%s\n' "${ASSIGNMENT_ROOT}"
  printf 'shared_results_root=%s\n' "${SHARED_RESULTS_ROOT}"
  printf 'shared_assignment_root=%s\n' "${SHARED_ASSIGNMENT_ROOT}"
  printf 'tmux_session_name=%s\n' "${TMUX_SESSION}"
  printf 'runner_label=%s\n' "${RUNNER_LABEL}"
  printf 'remote_launch_command=%s\n' "${RUNNER_CMD_STRING}"
  printf 'launch_timestamp=%s\n' "$(timestamp_utc)"
} > "${MANIFEST_FILE}"
printf '%s\n' "${RUNNER_CMD_STRING}" > "${RUNNER_COMMAND_FILE}"

write_phase "rebuild_image"
docker image rm -f "${IMAGE_TAG}" >/dev/null 2>&1 || true
(
  cd "${REPO_PATH}"
  ./scripts/ensure_provenance_image.sh --image "${IMAGE_TAG}" --rebuild
)

write_phase "reset_tmux"
if tmux has-session -t "${TMUX_SESSION}" >/dev/null 2>&1; then
  tmux kill-session -t "${TMUX_SESSION}"
fi

write_phase "write_tmux_wrapper"
cat > "${RUNNER_WRAPPER_SCRIPT}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

phase_file=$(printf '%q' "${PHASE_FILE}")
status_dir=$(printf '%q' "${STATUS_DIR}")
assignment_root=$(printf '%q' "${ASSIGNMENT_ROOT}")
shared_results_root=$(printf '%q' "${SHARED_RESULTS_ROOT}")
shared_assignment_root=$(printf '%q' "${SHARED_ASSIGNMENT_ROOT}")
repo_path=$(printf '%q' "${REPO_PATH}")
runner_log=$(printf '%q' "${RUNNER_LOG_FILE}")

printf 'running\n' > "\${phase_file}"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "\${status_dir}/runner_started_at.txt"

cd "\${repo_path}"
set +e
${RUNNER_CMD_STRING} 2>&1 | tee -a "\${runner_log}"
runner_rc=\${PIPESTATUS[0]}
set -e

case_root=""
for candidate in "\${assignment_root}"/20*; do
  [[ -d "\${candidate}" && -f "\${candidate}/manifest.txt" ]] || continue
  case_root="\${candidate}"
done
if [[ -n "\${case_root}" ]]; then
  printf '%s\n' "\${case_root}" > "\${status_dir}/latest_case_root.txt"
fi

printf '%s\n' "\${runner_rc}" > "\${status_dir}/runner_exit_code.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "\${status_dir}/runner_finished_at.txt"
printf '%s\n' "\${shared_assignment_root}" > "\${status_dir}/shared_assignment_root.txt"
printf 'in_progress\n' > "\${status_dir}/shared_copy_state.txt"
printf 'shared_copy\n' > "\${phase_file}"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "\${status_dir}/shared_copy_started_at.txt"

shared_copy_ok="false"
shared_parent=\$(dirname "\${shared_assignment_root}")
shared_stage="\${shared_parent}/.\$(basename "\${shared_assignment_root}").stage-\$(hostname)-\$$"
rm -rf "\${shared_stage}"
mkdir -p "\${shared_parent}"
if cp -a "\${assignment_root}" "\${shared_stage}"; then
  rm -rf "\${shared_assignment_root}"
  mv "\${shared_stage}" "\${shared_assignment_root}"
  shared_copy_ok="true"
else
  rm -rf "\${shared_stage}"
fi

if [[ "\${shared_copy_ok}" == "true" ]]; then
  printf 'done\n' > "\${status_dir}/shared_copy_state.txt"
else
  printf 'failed\n' > "\${status_dir}/shared_copy_state.txt"
fi
date -u +"%Y-%m-%dT%H:%M:%SZ" > "\${status_dir}/shared_copy_finished_at.txt"

if [[ "\${runner_rc}" -eq 0 ]]; then
  if [[ "\${shared_copy_ok}" == "true" ]]; then
    printf 'completed\n' > "\${phase_file}"
  else
    printf 'shared_copy_failed\n' > "\${phase_file}"
  fi
else
  printf 'runner_failed\n' > "\${phase_file}"
fi

exit "\${runner_rc}"
EOF
chmod +x "${RUNNER_WRAPPER_SCRIPT}"

write_phase "launch_tmux"
tmux new-session -d -s "${TMUX_SESSION}" "$(printf 'bash %q' "${RUNNER_WRAPPER_SCRIPT}")"
sleep 2
if ! tmux has-session -t "${TMUX_SESSION}" >/dev/null 2>&1 && [[ ! -f "${STATUS_DIR}/runner_exit_code.txt" ]]; then
  die "tmux session ${TMUX_SESSION} did not stay up long enough to confirm launch"
fi

write_phase "launched"
write_status_file "${STATUS_DIR}/tmux_session.txt" "${TMUX_SESSION}"
write_status_file "${STATUS_DIR}/launched_at.txt" "$(timestamp_utc)"

log "status=launched"
log "assignment_id=${ASSIGNMENT_ID}"
log "image_tag=${IMAGE_TAG}"
log "assignment_root=${ASSIGNMENT_ROOT}"
log "tmux_session=${TMUX_SESSION}"
