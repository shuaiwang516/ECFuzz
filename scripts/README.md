# Fuzzing Runner Scripts

This directory contains the Docker-based runners for longer ECFuzz experiments.

## Scripts

- [ensure_provenance_image.sh](/home/shuai/xlab/ecfuzz/ECFuzz/scripts/ensure_provenance_image.sh)
  - checks Docker availability
  - builds the provenance-enabled image from the current repository tree when missing
- [run_docker_fuzz_single.sh](/home/shuai/xlab/ecfuzz/ECFuzz/scripts/run_docker_fuzz_single.sh)
  - runs one project in one containerized fuzzing job
  - unit tests are always enabled
  - unit-test pass is always required before system test
  - launches the container with `--privileged`
  - runs `/home/hadoop/prepare.sh` inside the container before starting `fuzzer.py`
- [run_docker_fuzz_all.sh](/home/shuai/xlab/ecfuzz/ECFuzz/scripts/run_docker_fuzz_all.sh)
  - runs the five projects sequentially by calling `run_docker_fuzz_single.sh`

## Fresh-Machine Behavior

The runners are designed for a fresh but controlled setup:

- they do not require the provenance image to already exist
- they auto-build the image from `docker/param_tracking/Dockerfile` unless `--skip-image-ensure` is used
- they write host-side artifacts under `agent/verify/long_runs` by default

## Main Knobs

- `--tracking-mode on|off`
  - maps to `--exercise_guided_mutation`
- `--use-backed on|off|noop`
  - `on`: provenance agent active
  - `off`: provenance agent disabled
  - `noop`: provenance agent attached but not actively reporting use-backed signal
- `--run-hours <int>`
  - maps to `fuzzer.py --run_time`
- `--fuzzing-loop <int>`
  - maps to `fuzzer.py --fuzzing_loop`

## Examples

Single project, 1 hour, guided mutation on, use-backed provenance on:

```bash
scripts/run_docker_fuzz_single.sh \
  --project hbase \
  --run-hours 1 \
  --tracking-mode on \
  --use-backed on
```

All five projects, sequentially, 1 hour each:

```bash
scripts/run_docker_fuzz_all.sh \
  --run-hours 1 \
  --tracking-mode on \
  --use-backed on
```

Dry-run only:

```bash
scripts/run_docker_fuzz_all.sh \
  --run-hours 1 \
  --tracking-mode off \
  --use-backed off \
  --dry-run
```

## Outputs

Each single-project case creates:

- `output/`
- `comparison_metrics/`
- `param_tracking/`
- `logs/`
- `manifest.txt`

The batch runner creates:

- one subdirectory per project run
- `logs/<project>.log`
- `summary.tsv`
