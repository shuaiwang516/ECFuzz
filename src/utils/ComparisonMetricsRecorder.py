import json
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, Iterable, Optional

from dataModel.TestResult import TestResult
from dataModel.Testcase import Testcase
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.Logger import getLogger
from utils.ProvenanceTrackingState import ProvenanceTrackingState
from utils.ShowStats import ShowStats
from utils.UnitConstant import FUZZER_DIR, ROOT_DIR


class ComparisonMetricsRecorder(object):
    SNAPSHOT_HEADER = (
        "run_id\tproject\texercise_guided_mutation\telapsed_seconds\tloop_count\titeration_count\t"
        "queue_length\tunit_testcase_count\tunit_ctest_count\tsystem_testcase_count\taccepted_seed_count\t"
        "total_failures\ttotal_failures_type1\ttotal_failures_type2\ttotal_failures_type3\t"
        "distinct_exercised_params_cumulative\tdistinct_exercised_params_from_accepted_runs_cumulative\t"
        "nonzero_exercised_system_runs\tnonzero_exercised_accepted_system_runs\t"
        "distinct_use_backed_params_cumulative\tdistinct_use_backed_params_from_accepted_runs_cumulative\t"
        "nonzero_use_backed_system_runs\tnonzero_use_backed_accepted_system_runs\t"
        "average_unit_test_time\taverage_system_test_time\tecfuzz_exec_speed\n"
    )

    def __init__(self) -> None:
        self.logger = getLogger()
        self.project = Configuration.fuzzerConf["project"]
        self.enabledFlag = Configuration.fuzzerConf.get("exercise_guided_mutation", "False")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.runId = f"{timestamp}-{os.getpid()}"
        self.metricsRoot = Configuration.fuzzerConf.get(
            "comparison_metrics_dir",
            os.path.join(FUZZER_DIR, "comparison_metrics"),
        )
        self.runDir = os.path.join(
            self.metricsRoot,
            self.project,
            f"{self.runId}-guided-{self.enabledFlag}",
        )
        os.makedirs(self.runDir, exist_ok=True)
        self.snapshotPath = os.path.join(self.runDir, "snapshots.tsv")
        self.eventPath = os.path.join(self.runDir, "events.jsonl")
        self.summaryPath = os.path.join(self.runDir, "summary.json")
        self.metadataPath = os.path.join(self.runDir, "metadata.json")
        self.uniqueFailureSignatures = set()
        self.firstTimes: Dict[str, Optional[float]] = {
            "time_to_first_exercised_param": None,
            "time_to_first_use_backed_exercised_param": None,
            "time_to_first_failure": None,
            "time_to_first_type1_failure": None,
            "time_to_first_type2_failure": None,
            "time_to_first_type3_failure": None,
            "time_to_first_unique_failure_signature": None,
        }
        self.exercisedThresholdTimes: Dict[int, Optional[float]] = {
            10: None,
            50: None,
            100: None,
        }

        with open(self.snapshotPath, "w", encoding="utf-8") as fd:
            fd.write(self.SNAPSHOT_HEADER)
        with open(self.eventPath, "w", encoding="utf-8"):
            pass

        self._write_metadata()

    def _write_metadata(self) -> None:
        metadata = {
            "run_id": self.runId,
            "project": self.project,
            "exercise_guided_mutation": self.enabledFlag,
            "exercise_guided_explore_ratio": Configuration.fuzzerConf.get("exercise_guided_explore_ratio", ""),
            "use_provenance_agent": Configuration.fuzzerConf.get("use_provenance_agent", "False"),
            "provenance_agent_mode": Configuration.fuzzerConf.get("provenance_agent_mode", ""),
            "start_timestamp": datetime.now().isoformat(),
            "configured_run_time_hours": Configuration.fuzzerConf.get("run_time", ""),
            "configured_fuzzing_loop": Configuration.fuzzerConf.get("fuzzing_loop", ""),
            "mutator": Configuration.fuzzerConf.get("mutator", ""),
            "systemtester": Configuration.fuzzerConf.get("systemtester", ""),
            "docker_image_tag": os.environ.get("ECFUZZ_IMAGE_TAG", ""),
            "workspace_revision": self._workspace_revision(),
        }
        with open(self.metadataPath, "w", encoding="utf-8") as fd:
            json.dump(metadata, fd, indent=2, sort_keys=True)

    @staticmethod
    def _workspace_revision() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    @staticmethod
    def _elapsed_seconds() -> float:
        return max(0.0, time.time() - ShowStats.fuzzerStartTime)

    def _append_event(self, payload: Dict) -> None:
        with open(self.eventPath, "a", encoding="utf-8") as fd:
            fd.write(json.dumps(payload, sort_keys=True) + "\n")

    def record_snapshot(self) -> None:
        elapsed_seconds = self._elapsed_seconds()
        with open(self.snapshotPath, "a", encoding="utf-8") as fd:
            fd.write(
                f"{self.runId}\t{self.project}\t{self.enabledFlag}\t{elapsed_seconds:.3f}\t"
                f"{ShowStats.loopCounts}\t{ShowStats.iterationCounts}\t{ShowStats.queueLength}\t"
                f"{ShowStats.totalUnitTestcases}\t{ShowStats.totalRunUnitTestsCount}\t"
                f"{ShowStats.totalSystemTestcases}\t{ShowStats.acceptedSeedCount}\t"
                f"{ShowStats.totalSystemTestFailed}\t{ShowStats.totalSystemTestFailed_Type1}\t"
                f"{ShowStats.totalSystemTestFailed_Type2}\t{ShowStats.totalSystemTestFailed_Type3}\t"
                f"{len(ExerciseGuidanceState.projectGlobalExercisedParams)}\t"
                f"{len(ExerciseGuidanceState.projectAcceptedExercisedParams)}\t"
                f"{ExerciseGuidanceState.nonzeroSystemRuns}\t"
                f"{ExerciseGuidanceState.nonzeroAcceptedSystemRuns}\t"
                f"{len(ProvenanceTrackingState.projectGlobalUseBackedParams)}\t"
                f"{len(ProvenanceTrackingState.projectAcceptedUseBackedParams)}\t"
                f"{ProvenanceTrackingState.nonzeroUseBackedSystemRuns}\t"
                f"{ProvenanceTrackingState.nonzeroUseBackedAcceptedSystemRuns}\t"
                f"{ShowStats.averageUnitTestTime}\t{ShowStats.averageSystemTestTime}\t"
                f"{ShowStats.ecFuzzExecSpeed}\n"
            )

    def record_exercised_discovery(self, testcase: Testcase, param_name: str) -> None:
        elapsed_seconds = self._elapsed_seconds()
        if self.firstTimes["time_to_first_exercised_param"] is None:
            self.firstTimes["time_to_first_exercised_param"] = elapsed_seconds
        self._append_event(
            {
                "run_id": self.runId,
                "project": self.project,
                "exercise_guided_mutation": self.enabledFlag,
                "elapsed_seconds": elapsed_seconds,
                "event_type": "new_exercised_param",
                "testcase_id": testcase.fileName or testcase.filePath,
                "mutated_params": list(getattr(testcase, "mutatedConfNames", [])),
                "candidate_source": getattr(testcase, "mutationCandidateSource", "baseline"),
                "param_name": param_name,
            }
        )
        self._update_exercised_thresholds(elapsed_seconds)

    def _update_exercised_thresholds(self, elapsed_seconds: float) -> None:
        total_exercised = len(ExerciseGuidanceState.projectGlobalExercisedParams)
        for threshold in sorted(self.exercisedThresholdTimes.keys()):
            if total_exercised >= threshold and self.exercisedThresholdTimes[threshold] is None:
                self.exercisedThresholdTimes[threshold] = elapsed_seconds

    def record_use_backed_discovery(self, testcase: Testcase, param_name: str) -> None:
        elapsed_seconds = self._elapsed_seconds()
        if self.firstTimes["time_to_first_use_backed_exercised_param"] is None:
            self.firstTimes["time_to_first_use_backed_exercised_param"] = elapsed_seconds
        self._append_event(
            {
                "run_id": self.runId,
                "project": self.project,
                "exercise_guided_mutation": self.enabledFlag,
                "elapsed_seconds": elapsed_seconds,
                "event_type": "new_use_backed_exercised_param",
                "testcase_id": testcase.fileName or testcase.filePath,
                "mutated_params": list(getattr(testcase, "mutatedConfNames", [])),
                "candidate_source": getattr(testcase, "mutationCandidateSource", "baseline"),
                "param_name": param_name,
            }
        )

    def record_failure(self, testcase: Testcase, result: TestResult, failure_signature: str, exception_class: str) -> None:
        elapsed_seconds = self._elapsed_seconds()
        if self.firstTimes["time_to_first_failure"] is None:
            self.firstTimes["time_to_first_failure"] = elapsed_seconds
        type_key = f"time_to_first_type{result.sysFailType}_failure"
        if type_key in self.firstTimes and self.firstTimes[type_key] is None:
            self.firstTimes[type_key] = elapsed_seconds
        self._append_event(
            {
                "run_id": self.runId,
                "project": self.project,
                "exercise_guided_mutation": self.enabledFlag,
                "elapsed_seconds": elapsed_seconds,
                "event_type": "failure_observed",
                "testcase_id": testcase.fileName or testcase.filePath,
                "mutated_params": list(getattr(testcase, "mutatedConfNames", [])),
                "candidate_source": getattr(testcase, "mutationCandidateSource", "baseline"),
                "failure_type": result.sysFailType,
                "failure_signature": failure_signature,
                "exception_class": exception_class,
            }
        )
        if failure_signature and failure_signature not in self.uniqueFailureSignatures:
            self.uniqueFailureSignatures.add(failure_signature)
            if self.firstTimes["time_to_first_unique_failure_signature"] is None:
                self.firstTimes["time_to_first_unique_failure_signature"] = elapsed_seconds
            self._append_event(
                {
                    "run_id": self.runId,
                    "project": self.project,
                    "exercise_guided_mutation": self.enabledFlag,
                    "elapsed_seconds": elapsed_seconds,
                    "event_type": "new_failure_signature",
                    "testcase_id": testcase.fileName or testcase.filePath,
                    "mutated_params": list(getattr(testcase, "mutatedConfNames", [])),
                    "candidate_source": getattr(testcase, "mutationCandidateSource", "baseline"),
                    "failure_type": result.sysFailType,
                    "failure_signature": failure_signature,
                    "exception_class": exception_class,
                }
            )

    def record_bootstrap(self, testcase: Testcase, exercised_names: Iterable[str], result: Optional[TestResult]) -> None:
        elapsed_seconds = self._elapsed_seconds()
        self._append_event(
            {
                "run_id": self.runId,
                "project": self.project,
                "exercise_guided_mutation": self.enabledFlag,
                "elapsed_seconds": elapsed_seconds,
                "event_type": "bootstrap_completed",
                "testcase_id": testcase.fileName or testcase.filePath,
                "bootstrap_exercised_count": len(list(exercised_names)),
                "system_status": None if result is None else result.status,
            }
        )

    def finalize(self) -> None:
        elapsed_seconds = self._elapsed_seconds()
        summary = {
            "run_id": self.runId,
            "project": self.project,
            "exercise_guided_mutation": self.enabledFlag,
            "elapsed_seconds": elapsed_seconds,
            "distinct_exercised_params_cumulative": len(ExerciseGuidanceState.projectGlobalExercisedParams),
            "distinct_exercised_params_from_accepted_runs_cumulative": len(
                ExerciseGuidanceState.projectAcceptedExercisedParams
            ),
            "distinct_use_backed_params_cumulative": len(ProvenanceTrackingState.projectGlobalUseBackedParams),
            "distinct_use_backed_params_from_accepted_runs_cumulative": len(
                ProvenanceTrackingState.projectAcceptedUseBackedParams
            ),
            "nonzero_use_backed_system_runs": ProvenanceTrackingState.nonzeroUseBackedSystemRuns,
            "nonzero_use_backed_accepted_system_runs": ProvenanceTrackingState.nonzeroUseBackedAcceptedSystemRuns,
            "total_failures": ShowStats.totalSystemTestFailed,
            "total_failures_type1": ShowStats.totalSystemTestFailed_Type1,
            "total_failures_type2": ShowStats.totalSystemTestFailed_Type2,
            "total_failures_type3": ShowStats.totalSystemTestFailed_Type3,
            "unique_failure_signatures": len(self.uniqueFailureSignatures),
            "accepted_seed_count": ShowStats.acceptedSeedCount,
            "bootstrap_ran": ExerciseGuidanceState.bootstrapRan,
            "bootstrap_exercised_set_size": len(ExerciseGuidanceState.bootstrapExercisedParams),
            "bootstrap_use_backed_exercised_set_size": len(ProvenanceTrackingState.bootstrapUseBackedParams),
            "time_to_first_exercised_param": self.firstTimes["time_to_first_exercised_param"],
            "time_to_first_use_backed_exercised_param": self.firstTimes["time_to_first_use_backed_exercised_param"],
            "time_to_first_failure": self.firstTimes["time_to_first_failure"],
            "time_to_first_type1_failure": self.firstTimes["time_to_first_type1_failure"],
            "time_to_first_type2_failure": self.firstTimes["time_to_first_type2_failure"],
            "time_to_first_type3_failure": self.firstTimes["time_to_first_type3_failure"],
            "time_to_first_unique_failure_signature": self.firstTimes["time_to_first_unique_failure_signature"],
            "time_to_10_exercised_params": self.exercisedThresholdTimes[10],
            "time_to_50_exercised_params": self.exercisedThresholdTimes[50],
            "time_to_100_exercised_params": self.exercisedThresholdTimes[100],
        }
        with open(self.summaryPath, "w", encoding="utf-8") as fd:
            json.dump(summary, fd, indent=2, sort_keys=True)
