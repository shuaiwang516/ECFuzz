#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENSURE_IMAGE_SCRIPT="${ROOT_DIR}/scripts/ensure_provenance_image.sh"
DEFAULT_IMAGE="ecfuzz/ecfuzz-provenance-agent:local"
DEFAULT_OUT_ROOT="${ROOT_DIR}/agent/verify/long_runs"
PROJECTS=(hadoop-common hadoop-hdfs hbase zookeeper alluxio)

print_usage() {
  cat <<'EOF'
Usage:
  run_docker_fuzz_single.sh --project <name> [options]

Required:
  --project <name>                One of: hadoop-common, hadoop-hdfs, hbase, zookeeper, alluxio

Options:
  --run-hours <int>               Fuzzer --run_time in hours. Default: 1
  --fuzzing-loop <int>            Fuzzer --fuzzing_loop. Default: -1
  --tracking-mode <on|off>        Map to --exercise_guided_mutation. Default: off
  --guided <on|off>               Alias for --tracking-mode
  --use-backed <on|off|noop>      'on' => provenance active, 'off' => no provenance agent,
                                  'noop' => provenance agent attached in noop mode. Default: off
  --image <name>                  Docker image. Default: ecfuzz/ecfuzz-provenance-agent:local
  --out-root <dir>                Host output root. Default: agent/verify/long_runs
  --label <text>                  Extra suffix in case directory name
  --exercise-guided-explore-ratio <float>
                                  Optional override for --exercise_guided_explore_ratio
  --skip-image-ensure             Do not auto-build the docker image if missing
  --rebuild-image                 Force rebuild of the docker image before running
  --dry-run                       Print the docker command and exit
  --help                          Show this help

Behavior:
  - Unit tests are always enabled: --skip_unit_test=False
  - Unit-test pass is required before system test: --require_unit_pass_for_system_test=True
  - The container is started with --privileged and runs /home/hadoop/prepare.sh before fuzzing
  - Outputs are mounted to:
      <case>/output
      <case>/comparison_metrics
      <case>/param_tracking
      <case>/logs
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

is_valid_project() {
  local candidate="$1"
  local project
  for project in "${PROJECTS[@]}"; do
    if [[ "${project}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
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

PROJECT=""
RUN_HOURS="1"
FUZZING_LOOP="-1"
TRACKING_MODE="off"
USE_BACKED="off"
IMAGE_NAME="${DEFAULT_IMAGE}"
OUT_ROOT="${DEFAULT_OUT_ROOT}"
LABEL=""
DRY_RUN="false"
EXPLORE_RATIO=""
ENSURE_IMAGE="true"
REBUILD_IMAGE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      require_value "$1" "${2:-}"
      PROJECT="$2"
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
    --skip-image-ensure)
      ENSURE_IMAGE="false"
      shift
      ;;
    --rebuild-image)
      REBUILD_IMAGE="true"
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

if [[ -z "${PROJECT}" ]]; then
  echo "--project is required" >&2
  print_usage >&2
  exit 1
fi

if ! is_valid_project "${PROJECT}"; then
  echo "invalid project: ${PROJECT}" >&2
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

CASE_NAME="${TIMESTAMP}-${PROJECT}-guided-${TRACKING_MODE}-usebacked-${USE_BACKED}${SAFE_LABEL}"
CASE_ROOT="${OUT_ROOT}/${CASE_NAME}"
OUTPUT_DIR="${CASE_ROOT}/output"
METRICS_DIR="${CASE_ROOT}/comparison_metrics"
TRACE_DIR="${CASE_ROOT}/param_tracking"
LOG_DIR="${CASE_ROOT}/logs"
LOG_FILE="${LOG_DIR}/fuzzer.log"
MANIFEST_FILE="${CASE_ROOT}/manifest.txt"
PREP_LOG_IN_CONTAINER="/home/hadoop/ecfuzz/agent_runner_logs/prepare.log"

mkdir -p "${OUTPUT_DIR}" "${METRICS_DIR}" "${TRACE_DIR}" "${LOG_DIR}"
chmod -R 777 "${CASE_ROOT}"

EXERCISE_GUIDED_VALUE="False"
if [[ "${TRACKING_MODE}" == "on" ]]; then
  EXERCISE_GUIDED_VALUE="True"
fi

USE_PROVENANCE_VALUE="False"
PROVENANCE_MODE_VALUE=""
case "${USE_BACKED}" in
  on)
    USE_PROVENANCE_VALUE="True"
    PROVENANCE_MODE_VALUE="active"
    ;;
  noop)
    USE_PROVENANCE_VALUE="True"
    PROVENANCE_MODE_VALUE="noop"
    ;;
  off)
    ;;
esac

FUZ_CMD=(
  python3 src/fuzzer.py
  "--project=${PROJECT}"
  "--run_time=${RUN_HOURS}"
  "--fuzzing_loop=${FUZZING_LOOP}"
  "--skip_unit_test=False"
  "--require_unit_pass_for_system_test=True"
  "--exercise_guided_mutation=${EXERCISE_GUIDED_VALUE}"
  "--use_provenance_agent=${USE_PROVENANCE_VALUE}"
)

if [[ -n "${PROVENANCE_MODE_VALUE}" ]]; then
  FUZ_CMD+=("--provenance_agent_mode=${PROVENANCE_MODE_VALUE}")
fi

if [[ -n "${EXPLORE_RATIO}" ]]; then
  FUZ_CMD+=("--exercise_guided_explore_ratio=${EXPLORE_RATIO}")
fi

FUZ_CMD_STRING="$(printf '%q ' "${FUZ_CMD[@]}")"
read -r -d '' INNER_CMD <<EOF || true
set -euo pipefail
mkdir -p /home/hadoop/ecfuzz/agent_runner_logs
cat >/etc/sudoers.d/hadoop-nopasswd <<'EOSUDO'
Defaults:hadoop !requiretty
hadoop ALL=(ALL) NOPASSWD:ALL
EOSUDO
chmod 440 /etc/sudoers.d/hadoop-nopasswd
cd /home/hadoop
echo "[runner] starting prepare.sh"
if ! timeout 1800s sudo -u hadoop -H bash -lc 'cd /home/hadoop && bash prepare.sh' >"${PREP_LOG_IN_CONTAINER}" 2>&1; then
  echo "[runner] prepare.sh failed; showing tail of ${PREP_LOG_IN_CONTAINER}" >&2
  tail -n 200 "${PREP_LOG_IN_CONTAINER}" >&2 || true
  exit 1
fi
echo "[runner] prepare.sh completed"
cd /home/hadoop/ecfuzz
set +e
sudo -u hadoop -H bash -lc $(printf '%q' "${FUZ_CMD_STRING}")
fuzz_rc=\$?
set -e
cp -f /home/hadoop/ecfuzz/data/fuzzer/fuzzer.log /home/hadoop/ecfuzz/agent_runner_logs/internal_fuzzer.log 2>/dev/null || true
exit "\${fuzz_rc}"
EOF

DOCKER_CMD=(
  docker run --rm --privileged --user 0:0
  -e "ECFUZZ_IMAGE_TAG=${IMAGE_NAME}"
  -v "${OUTPUT_DIR}:/home/hadoop/ecfuzz/data/fuzzer/output"
  -v "${METRICS_DIR}:/home/hadoop/ecfuzz/data/fuzzer/comparison_metrics"
  -v "${TRACE_DIR}:/home/hadoop/ecfuzz/data/fuzzer/param_tracking"
  -v "${LOG_DIR}:/home/hadoop/ecfuzz/agent_runner_logs"
  "${IMAGE_NAME}"
  bash -lc "${INNER_CMD}"
)

{
  echo "case_name=${CASE_NAME}"
  echo "project=${PROJECT}"
  echo "run_hours=${RUN_HOURS}"
  echo "fuzzing_loop=${FUZZING_LOOP}"
  echo "tracking_mode=${TRACKING_MODE}"
  echo "use_backed=${USE_BACKED}"
  echo "image=${IMAGE_NAME}"
  echo "output_dir=${OUTPUT_DIR}"
  echo "comparison_metrics_dir=${METRICS_DIR}"
  echo "param_tracking_dir=${TRACE_DIR}"
  echo "prepare_log_in_container=${PREP_LOG_IN_CONTAINER}"
  echo "uses_privileged=true"
  echo "command=${INNER_CMD}"
} >"${MANIFEST_FILE}"

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "case_root=${CASE_ROOT}"
  printf '%q ' "${DOCKER_CMD[@]}"
  printf '\n'
  exit 0
fi

if [[ "${ENSURE_IMAGE}" == "true" ]]; then
  ensure_cmd=("${ENSURE_IMAGE_SCRIPT}" "--image" "${IMAGE_NAME}" "--quiet")
  if [[ "${REBUILD_IMAGE}" == "true" ]]; then
    ensure_cmd+=("--rebuild")
  fi
  "${ensure_cmd[@]}"
fi

echo "==> ${CASE_NAME}"
printf '%q ' "${DOCKER_CMD[@]}" >"${LOG_DIR}/docker_command.sh"
printf '\n' >>"${LOG_DIR}/docker_command.sh"

"${DOCKER_CMD[@]}" 2>&1 | tee "${LOG_FILE}"

docker run --rm --user 0:0 \
  -v "${CASE_ROOT}:/mnt/case" \
  "${IMAGE_NAME}" \
  bash -lc "chmod -R a+rwx /mnt/case" >/dev/null

echo "case_root=${CASE_ROOT}"
