#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=${IMAGE_NAME:-ecfuzz-param-tracked}
FUZZING_LOOPS=${FUZZING_LOOPS:-10}
OUTPUT_ROOT=${1:-$(pwd)/docker/param_tracking/results}
PROJECTS=(hadoop-common hadoop-hdfs hbase zookeeper alluxio)

mkdir -p "${OUTPUT_ROOT}"

for project in "${PROJECTS[@]}"; do
  container_name="param-track-${project//[^a-z0-9]/-}"
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
  docker run -d --privileged --name "${container_name}" "${IMAGE_NAME}" tail -f /dev/null >/dev/null

  docker exec "${container_name}" bash -lc "bash /home/hadoop/prepare.sh"
  docker exec "${container_name}" bash -lc \
    "cd /home/hadoop/ecfuzz/src && python3 fuzzer.py --project=${project} --fuzzing_loop=${FUZZING_LOOPS}"

  mkdir -p "${OUTPUT_ROOT}/${project}"
  docker cp "${container_name}:/home/hadoop/ecfuzz/data/fuzzer/param_tracking/${project}/." "${OUTPUT_ROOT}/${project}/"
  docker cp "${container_name}:/home/hadoop/ecfuzz/data/fuzzer/fuzzer.log" "${OUTPUT_ROOT}/${project}/fuzzer.log"
  docker rm -f "${container_name}" >/dev/null
done

python3 docker/param_tracking/aggregate_param_tracking.py "${OUTPUT_ROOT}"
