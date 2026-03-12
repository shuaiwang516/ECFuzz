import json
import os
import sys
import tempfile
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from dataModel.TestResult import TestResult
from dataModel.Testcase import Testcase
from utils.ComparisonMetricsRecorder import ComparisonMetricsRecorder
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.ShowStats import ShowStats


class TestComparisonMetricsRecorder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})

    def setUp(self) -> None:
        ShowStats.fuzzerStartTime = time.time() - 1
        ShowStats.loopCounts = 1
        ShowStats.iterationCounts = 2
        ShowStats.queueLength = 3
        ShowStats.totalUnitTestcases = 4
        ShowStats.totalRunUnitTestsCount = 5
        ShowStats.totalSystemTestcases = 6
        ShowStats.acceptedSeedCount = 1
        ShowStats.totalSystemTestFailed = 2
        ShowStats.totalSystemTestFailed_Type1 = 1
        ShowStats.totalSystemTestFailed_Type2 = 1
        ShowStats.totalSystemTestFailed_Type3 = 0
        ShowStats.averageUnitTestTime = 1.5
        ShowStats.averageSystemTestTime = 2.5
        ShowStats.ecFuzzExecSpeed = 0.5
        ExerciseGuidanceState.configure_from_current()

    def test_recorder_writes_snapshot_events_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Configuration.fuzzerConf["comparison_metrics_dir"] = tmpdir
            Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
            ExerciseGuidanceState.configure_from_current()
            recorder = ComparisonMetricsRecorder()
            testcase = Testcase()
            testcase.fileName = "Testcase-1"
            testcase.mutatedConfNames = ["dfs.replication"]
            testcase.mutationCandidateSource = "project-global"

            ExerciseGuidanceState.projectGlobalExercisedParams = {"dfs.replication"}
            recorder.record_exercised_discovery(testcase, "dfs.replication")
            recorder.record_failure(
                testcase,
                TestResult(status=1, sysFailType=2),
                "sysFailType:2:IllegalArgumentException",
                "IllegalArgumentException",
            )
            recorder.record_snapshot()
            recorder.finalize()

            self.assertTrue(os.path.exists(recorder.snapshotPath))
            self.assertTrue(os.path.exists(recorder.eventPath))
            self.assertTrue(os.path.exists(recorder.summaryPath))

            with open(recorder.summaryPath, "r", encoding="utf-8") as fd:
                summary = json.load(fd)

            self.assertEqual(1, summary["distinct_exercised_params_cumulative"])
            self.assertEqual(2, summary["total_failures"])
            self.assertIsNotNone(summary["time_to_first_exercised_param"])
            self.assertIsNotNone(summary["time_to_first_failure"])


if __name__ == "__main__":
    unittest.main()
