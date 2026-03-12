#!/usr/bin/env python3
import csv
import json
import statistics
import sys
from pathlib import Path


def read_counts(summary_path: Path):
    counts = []
    params = set()
    with summary_path.open(encoding="utf-8") as fd:
        reader = csv.DictReader(fd, delimiter="\t")
        for row in reader:
            counts.append(int(row["unique_params"]))
            params.update(filter(None, row["params"].split(",")))
    return counts, sorted(params)


def summarize(project_dir: Path):
    summaries = sorted(project_dir.rglob("summary.tsv"))
    project_counts = []
    project_params = set()
    run_payloads = []
    for summary in summaries:
        counts, params = read_counts(summary)
        if not counts:
            continue
        project_counts.extend(counts)
        project_params.update(params)
        run_payloads.append(
            {
                "summary_path": str(summary),
                "testcase_count": len(counts),
                "nonzero_testcase_count": sum(1 for count in counts if count > 0),
                "counts": counts,
                "distinct_param_count": len(params),
                "distinct_params": params,
                "mean": statistics.fmean(counts),
                "min": min(counts),
                "max": max(counts),
            }
        )
    if not project_counts:
        return None
    return {
        "project": project_dir.name,
        "run_count": len(run_payloads),
        "testcase_count": len(project_counts),
        "nonzero_testcase_count": sum(1 for count in project_counts if count > 0),
        "distinct_param_count": len(project_params),
        "distinct_params": sorted(project_params),
        "mean": statistics.fmean(project_counts),
        "min": min(project_counts),
        "max": max(project_counts),
        "runs": run_payloads,
    }


def main():
    if len(sys.argv) != 2:
        print("usage: aggregate_param_tracking.py <results_dir>", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    output_rows = []
    output_payload = []

    for project_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        summary = summarize(project_dir)
        if summary is None:
            continue
        output_payload.append(summary)
        output_rows.append(
            [
                summary["project"],
                str(summary["run_count"]),
                str(summary["testcase_count"]),
                str(summary["nonzero_testcase_count"]),
                str(summary["distinct_param_count"]),
                f"{summary['mean']:.2f}",
                str(summary["min"]),
                str(summary["max"]),
            ]
        )

    aggregate_tsv = root / "aggregate.tsv"
    with aggregate_tsv.open("w", encoding="utf-8", newline="") as fd:
        writer = csv.writer(fd, delimiter="\t")
        writer.writerow(
            [
                "project",
                "runs",
                "testcases",
                "nonzero_testcases",
                "distinct_params",
                "mean_unique_params",
                "min",
                "max",
            ]
        )
        writer.writerows(output_rows)

    aggregate_json = root / "aggregate.json"
    with aggregate_json.open("w", encoding="utf-8") as fd:
        json.dump(output_payload, fd, indent=2)


if __name__ == "__main__":
    main()
