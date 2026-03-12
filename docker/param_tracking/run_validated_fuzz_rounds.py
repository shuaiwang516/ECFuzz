#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECTS = ["hadoop-common", "hadoop-hdfs", "hbase", "zookeeper", "alluxio"]
CONTAINER_TRACK_ROOT = Path("/home/hadoop/ecfuzz/data/fuzzer/param_tracking")
CONTAINER_FUZZER_ROOT = Path("/home/hadoop/ecfuzz/data/fuzzer")


def run_cmd(cmd: List[str], check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def docker_exec(container: str, shell_cmd: str, env: Dict[str, str] = None, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    for key, value in (env or {}).items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend([container, "bash", "-lc", shell_cmd])
    return run_cmd(cmd, check=check)


def docker_cp(container: str, src: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(["docker", "cp", f"{container}:{src}", str(dst)])


def container_path_exists(container: str, path: str) -> bool:
    result = docker_exec(container, f"test -e {shlex.quote(path)}", check=False)
    return result.returncode == 0


def run_prepare(container: str, retries: int = 3, retry_sleep: int = 5) -> None:
    failures = []
    for attempt in range(1, retries + 1):
        result = docker_exec(container, "bash /home/hadoop/prepare.sh", check=False)
        if result.returncode == 0:
            if attempt > 1:
                print(f"[{container}] prepare succeeded on retry {attempt}")
            return

        failures.append(
            {
                "attempt": attempt,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
        print(f"[{container}] prepare attempt {attempt} failed with code {result.returncode}")
        if attempt < retries:
            time.sleep(retry_sleep)

    tail = failures[-1]
    raise RuntimeError(
        f"{container}: prepare.sh failed after {retries} attempts with code {tail['returncode']}\n"
        f"stdout tail:\n{tail['stdout']}\n\nstderr tail:\n{tail['stderr']}"
    )


def latest_run_info(container: str, project: str) -> Dict[str, object]:
    script = r"""
import csv
import json
import os
from pathlib import Path

project = os.environ["PROJECT"]
root = Path("/home/hadoop/ecfuzz/data/fuzzer/param_tracking") / project
runs = [path for path in root.iterdir() if path.is_dir()]
if not runs:
    raise SystemExit("no param-tracking runs found")
latest = max(runs, key=lambda path: path.stat().st_mtime_ns)
rows = []
with open(latest / "summary.tsv", encoding="utf-8") as fd:
    reader = csv.DictReader(fd, delimiter="\t")
    rows.extend(reader)
accepted = [row["testcase_id"] for row in rows if row["unit_status"] == "0" and row["system_status"]]
print(json.dumps({
    "run_id": latest.name,
    "run_path": str(latest),
    "row_count": len(rows),
    "accepted_ids": accepted,
    "rejected_ids": [row["testcase_id"] for row in rows if row["testcase_id"] not in accepted],
    "rows": rows,
}))
"""
    result = docker_exec(container, f"python3 - <<'PY'\n{script}\nPY", env={"PROJECT": project})
    return json.loads(result.stdout)


def copy_attempt_artifacts(container: str, project: str, attempt_dir: Path, run_id: str) -> None:
    docker_cp(container, str(CONTAINER_TRACK_ROOT / project / run_id), attempt_dir)
    docker_cp(container, str(CONTAINER_FUZZER_ROOT / "fuzzer.log"), attempt_dir / "fuzzer.log")

    for artifact in ["ut_results", "st_results", "ut_testcases", "st_fail_testcases"]:
        artifact_path = str(CONTAINER_FUZZER_ROOT / artifact)
        if container_path_exists(container, artifact_path):
            docker_cp(container, artifact_path, attempt_dir)


def write_attempt_row(attempts_tsv: Path, row: List[str], write_header: bool) -> None:
    with attempts_tsv.open("a", encoding="utf-8", newline="") as fd:
        writer = csv.writer(fd, delimiter="\t")
        if write_header:
            writer.writerow(
                [
                    "attempt",
                    "run_id",
                    "rows",
                    "accepted_rows",
                    "rejected_rows",
                    "accepted_selected",
                    "cumulative_selected",
                ]
            )
        writer.writerow(row)


def update_manifest(
    manifest_path: Path,
    manifest: Dict[str, object],
    project: str,
    target_accepted: int,
    attempts_used: int,
    selected_rows: List[Dict[str, object]],
) -> None:
    manifest["projects"][project] = {
        "target_accepted": target_accepted,
        "attempts_used": attempts_used,
        "selected_rows": selected_rows,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ECFuzz batches with strict unit-test gating.")
    parser.add_argument("--image-name", default="ecfuzz-param-tracked")
    parser.add_argument("--target-accepted", type=int, default=10)
    parser.add_argument("--max-attempts", type=int, default=80)
    parser.add_argument("--projects", nargs="+", default=DEFAULT_PROJECTS)
    parser.add_argument("--output-root")
    parser.add_argument("--container-suffix", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.output_root:
        output_root = Path(args.output_root).resolve()
    else:
        output_root = (REPO_ROOT / "docker" / "param_tracking" / "results" / f"validated-{timestamp}").resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_path = output_root / "accepted_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"output_root": str(output_root), "projects": {}}

    for project in args.projects:
        suffix = f"-{args.container_suffix}" if args.container_suffix else ""
        container_name = f"param-track-valid-{project.replace('-', '')}{suffix}"
        project_dir = output_root / project
        attempts_dir = project_dir / "attempts"
        attempts_dir.mkdir(parents=True, exist_ok=True)
        attempts_tsv = project_dir / "attempts.tsv"
        existing_project = manifest["projects"].get(project, {})
        selected_rows = list(existing_project.get("selected_rows", []))
        selected_count = len(selected_rows)
        existing_attempt_dirs = sorted(
            (
                int(path.name.split("-")[-1])
                for path in attempts_dir.glob("attempt-*")
                if path.is_dir() and path.name.split("-")[-1].isdigit()
            ),
            reverse=True,
        )
        attempt = existing_attempt_dirs[0] if existing_attempt_dirs else 0

        run_cmd(["docker", "rm", "-f", container_name], check=False)
        run_cmd(
            ["docker", "run", "-d", "--privileged", "--name", container_name, args.image_name, "tail", "-f", "/dev/null"],
            capture_output=False,
        )
        try:
            run_prepare(container_name)

            while selected_count < args.target_accepted:
                attempt += 1
                if attempt > args.max_attempts:
                    raise RuntimeError(
                        f"{project}: only collected {selected_count}/{args.target_accepted} accepted executions "
                        f"after {args.max_attempts} attempts"
                    )

                fuzz_cmd = (
                    "cd /home/hadoop/ecfuzz/src && "
                    f"python3 fuzzer.py --project={project} --fuzzing_loop=1 "
                    "--skip_unit_test=False --force_system_testing_ratio=1 "
                    "--require_unit_pass_for_system_test=True"
                )
                result = docker_exec(container_name, fuzz_cmd, check=False)
                if result.returncode != 0:
                    raise RuntimeError(
                        f"{project}: fuzzing attempt {attempt} failed with code {result.returncode}\n"
                        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
                    )

                info = latest_run_info(container_name, project)
                attempt_dir = attempts_dir / f"attempt-{attempt:03d}"
                if attempt_dir.exists():
                    shutil.rmtree(attempt_dir)
                attempt_dir.mkdir(parents=True, exist_ok=True)
                copy_attempt_artifacts(container_name, project, attempt_dir, str(info["run_id"]))

                remaining = args.target_accepted - selected_count
                accepted_ids = list(info["accepted_ids"])
                selected_ids = accepted_ids[:remaining]
                for testcase_id in selected_ids:
                    selected_rows.append(
                        {
                            "project": project,
                            "attempt": attempt,
                            "run_id": info["run_id"],
                            "testcase_id": testcase_id,
                            "json_path": str((attempt_dir / str(info["run_id"]) / f"{testcase_id}.json").resolve()),
                            "summary_path": str((attempt_dir / str(info["run_id"]) / "summary.tsv").resolve()),
                            "fuzzer_log": str((attempt_dir / "fuzzer.log").resolve()),
                        }
                    )
                selected_count += len(selected_ids)

                write_attempt_row(
                    attempts_tsv,
                    [
                        str(attempt),
                        str(info["run_id"]),
                        str(info["row_count"]),
                        str(len(accepted_ids)),
                        str(len(info["rejected_ids"])),
                        str(len(selected_ids)),
                        str(selected_count),
                    ],
                    write_header=attempts_tsv.exists() is False or attempts_tsv.stat().st_size == 0,
                )
                update_manifest(
                    manifest_path,
                    manifest,
                    project,
                    args.target_accepted,
                    attempt,
                    selected_rows,
                )

                print(
                    f"[{project}] attempt {attempt}: accepted {len(accepted_ids)} rows, "
                    f"selected {len(selected_ids)}, cumulative {selected_count}/{args.target_accepted}"
                )

        finally:
            run_cmd(["docker", "rm", "-f", container_name], check=False)

        update_manifest(
            manifest_path,
            manifest,
            project,
            args.target_accepted,
            attempt,
            selected_rows,
        )
    print(manifest_path)


if __name__ == "__main__":
    main()
