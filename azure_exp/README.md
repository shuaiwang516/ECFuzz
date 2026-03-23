# Azure Experiment Orchestration

This directory contains a controller-side orchestration layer for running the 10 required ECFuzz combinations across 10 machines.

The controller directory name remains `azure_exp`, but the current defaults are set up for the CloudLab cluster layout.

It is intentionally built around the existing verified single-run wrapper:

- `scripts/run_docker_fuzz_single.sh`

It does not center the implementation on `scripts/run_docker_fuzz_all.sh`.

## What It Does

- each VM runs exactly one `(project, mode)` combination
- each remote run is prepared as a fresh-machine workflow
- each VM clones the default branch from `https://github.com/shuaiwang516/ECFuzz.git`
- each VM removes the target Docker image if it exists, then rebuilds a fresh image from the fresh clone
- each VM launches fuzzing inside a fresh tmux session named `ecfuzzExp`
- both modes explicitly use unit tests because the verified single-run wrapper always enforces:
  - `--skip_unit_test=False`
  - `--require_unit_pass_for_system_test=True`
- monitoring prints live high-signal status and also pulls manifests/logs back under `azure_exp/collected/...`

## Files

- [launch_azure_batch.sh](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/launch_azure_batch.sh): controller launcher
- [monitor_azure_batch.sh](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/monitor_azure_batch.sh): live monitor plus metadata collection
- [remote_bootstrap_and_run.sh](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/remote_bootstrap_and_run.sh): remote bootstrap/provision/clone/build/tmux entrypoint
- [lib.sh](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/lib.sh): shared validation and SSH helpers
- [assignments.example.tsv](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/assignments.example.tsv): example 10-row assignment file

## Inventory Format

The launcher and monitor read [machine_list.txt](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/machine_list.txt) from `azure_exp/` by default.

Each line must be a full SSH command, for example:

```text
ssh -o BatchMode=yes azureuser@vm-01.example
ssh -o BatchMode=yes azureuser@vm-02.example
```

Important constraints:

- line numbers are physical 1-based file line numbers
- blank lines are not allowed
- comment lines are not allowed
- assignments reference machines by line number, not by hostname

The monitor uses tar-over-SSH rather than `scp`, so full SSH commands with options remain usable.

## Assignment File Format

Use a TSV file with header:

```text
machine_line	project	mode	run_hours	label
```

`label` may be empty, but the 10 required combinations must still be covered exactly once.

Supported projects:

- `hadoop-common`
- `hadoop-hdfs`
- `hbase`
- `zookeeper`
- `alluxio`

Supported modes:

- `ECFuzz`
  - unit tests enabled
  - tracking off
  - use_backed off
- `ECFuzzParamTracking`
  - unit tests enabled
  - tracking on
  - use_backed on

Validation is strict:

- invalid machine line: fail
- invalid project: fail
- invalid mode: fail
- duplicate machine assignment: fail
- duplicate `(project, mode)` assignment: fail
- anything other than all 10 unique combinations exactly once: fail

## Remote Layout

The remote defaults now match the CloudLab layout:

- machine-local base dir: `/users/swang516`
- Docker data-root: `/users/swang516/docker`
- repo clone: `/users/swang516/ECFuzz`
- experiment root: `/users/swang516/azure_exp`
- per-assignment root: `/users/swang516/azure_exp/runs/<assignment_id>`
- shared results root: `/proj/uptesting/ecfuzz-shared-results/<assignment_id>`

Each remote assignment root stores:

- `assignment_manifest.txt`
- `status/`
- one case directory created by `scripts/run_docker_fuzz_single.sh`

After the runner finishes, the remote wrapper copies the full assignment directory into the shared results root. Running state stays machine-local; only finished artifacts are published to the shared directory.

The case directory still uses Docker bind mounts for:

- `output/`
- `comparison_metrics/`
- `param_tracking/`
- `logs/`

## Launch

Validate and print the resolved plan without contacting any VM:

```bash
bash azure_exp/launch_azure_batch.sh \
  --machine-list azure_exp/machine_list.txt \
  --assignments azure_exp/assignments.example.tsv \
  --batch-id cloudlab-demo \
  --dry-run
```

Real launch:

```bash
bash azure_exp/launch_azure_batch.sh \
  --machine-list azure_exp/machine_list.txt \
  --assignments /path/to/assignments.tsv \
  --batch-id cloudlab-20260321-all10 \
  --parallelism 10
```

Launcher behavior:

- validates `azure_exp/machine_list.txt`
- validates the assignment TSV against the exact 10-combination matrix
- resolves each `machine_line` to its SSH command
- checks that each machine has root access, either directly or through non-interactive `sudo`
- launches the machine bootstraps concurrently
- streams [remote_bootstrap_and_run.sh](/home/shuai/xlab/ecfuzz/ECFuzz/azure_exp/remote_bootstrap_and_run.sh) to the target host over SSH
- the remote script installs `docker.io`, `git`, `tmux`, and `ca-certificates`
- rewrites `/etc/docker/daemon.json` to use `/users/swang516/docker`
- clones the repo fresh from GitHub default branch
- removes the target image if it exists
- rebuilds the image from the fresh clone
- kills existing tmux session `ecfuzzExp` if present
- starts a fresh `ecfuzzExp` session running `scripts/run_docker_fuzz_single.sh`
- copies the finished assignment directory into `/proj/uptesting/ecfuzz-shared-results/<assignment_id>`

Per-launch controller logs are written at runtime under `azure_exp/launch_logs/<batch-id>/`.

## Monitor

Single pass:

```bash
bash azure_exp/monitor_azure_batch.sh \
  --machine-list azure_exp/machine_list.txt \
  --assignments /path/to/assignments.tsv \
  --batch-id cloudlab-20260321-all10 \
  --once
```

Continuous polling:

```bash
bash azure_exp/monitor_azure_batch.sh \
  --machine-list azure_exp/machine_list.txt \
  --assignments /path/to/assignments.tsv \
  --batch-id cloudlab-20260321-all10 \
  --interval-seconds 60
```

Monitor behavior per assignment:

- checks SSH reachability
- checks whether tmux session `ecfuzzExp` exists
- reads remote phase/status metadata
- falls back to the shared results copy if the machine-local assignment root is gone
- locates the current case directory
- prints machine line, project, mode, image, assignment root, state root, case root, tmux state, and current state
- tails recent `fuzzer.log` lines when present
- pulls selected artifacts to `azure_exp/collected/<batch-id>/<assignment_id>/`

Collected files include:

- `assignment_manifest.txt`
- `status/*`
- case `manifest.txt`
- `logs/prepare.log`
- `logs/fuzzer.log`
- `logs/docker_command.sh`
- `logs/internal_fuzzer.log` if present
- small summary files if present

## Local Verification

These checks do not contact remote VMs:

```bash
bash -n azure_exp/lib.sh \
  azure_exp/launch_azure_batch.sh \
  azure_exp/remote_bootstrap_and_run.sh \
  azure_exp/monitor_azure_batch.sh
```

```bash
bash azure_exp/launch_azure_batch.sh \
  --machine-list /tmp/machine_list.txt \
  --assignments azure_exp/assignments.example.tsv \
  --batch-id verify-azure \
  --dry-run
```

```bash
bash azure_exp/monitor_azure_batch.sh \
  --machine-list /tmp/machine_list.txt \
  --assignments azure_exp/assignments.example.tsv \
  --batch-id verify-azure \
  --once \
  --dry-run
```

## Assumptions

- remote machines are Ubuntu 22.04
- the SSH target can either be root directly or a user with non-interactive `sudo`
- key-based SSH is already configured
- the machines are treated as fresh enough that replacing `/etc/docker/daemon.json` with only the `data-root` setting is acceptable
- `/proj/uptesting/ecfuzz-shared-results` is writable from each machine for post-run artifact publishing
