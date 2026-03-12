import os
import queue
import sys
import tempfile
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from dataModel.TestResult import TestResult
from testValidator.TestValidator import TestValidator
from utils.ConfAnalyzer import ConfAnalyzer
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.ShowStats import ShowStats


class DummySystemTester(object):
    def __init__(self):
        self.lastExercisedConfNames = []
        self.lastTraceEvents = []
        self.called = 0

    def runTest(self, testcase, stopSoon, recordStats=True):
        self.called += 1
        self.lastExercisedConfNames = ["bootstrap.a", "bootstrap.b"]
        self.lastTraceEvents = [
            {"operation": "EXERCISED", "param_name": "bootstrap.a"},
            {"operation": "EXERCISED", "param_name": "bootstrap.b"},
        ]
        return TestResult(status=0)


class TestExerciseBootstrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})
        ConfAnalyzer.analyzeConfItems()

    def setUp(self) -> None:
        ShowStats.fuzzerStartTime = time.time()
        ShowStats.totalSystemTestcases = 0

    def test_bootstrap_populates_project_exercised_state_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
            Configuration.fuzzerConf["comparison_metrics_dir"] = tmpdir
            ExerciseGuidanceState.configure_from_current()
            validator = TestValidator()
            validator.sysTester = DummySystemTester()

            validator.runExerciseBootstrap(queue.Queue())
            validator.runExerciseBootstrap(queue.Queue())

            self.assertTrue(ExerciseGuidanceState.bootstrapComplete)
            self.assertEqual({"bootstrap.a", "bootstrap.b"}, ExerciseGuidanceState.projectGlobalExercisedParams)
            self.assertEqual(1, validator.sysTester.called)


if __name__ == "__main__":
    unittest.main()
