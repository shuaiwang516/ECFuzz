import os
import sys
import unittest
from unittest import mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from dataModel.ConfItem import ConfItem
from dataModel.Seed import Seed
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState


class TestExerciseGuidanceState(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})

    def setUp(self) -> None:
        Configuration.fuzzerConf["exercise_guided_mutation"] = "False"
        Configuration.fuzzerConf["exercise_guided_explore_ratio"] = "0.10"
        ExerciseGuidanceState.configure_from_current()

    def test_choose_candidate_names_off_returns_baseline_universe(self):
        seed = Seed([ConfItem("a", "INT", "1"), ConfItem("b", "INT", "2")])
        with mock.patch("utils.ExerciseGuidanceState.random.random", return_value=0.9):
            names, source = ExerciseGuidanceState.choose_candidate_names(["a", "b"], seed=seed)

        self.assertEqual(["a", "b"], names)
        self.assertEqual("baseline", source)

    def test_choose_candidate_names_prefers_seed_local_when_enabled(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        ExerciseGuidanceState.configure_from_current()
        seed = Seed([ConfItem("a", "INT", "1"), ConfItem("b", "INT", "2")])
        seed.lastExercisedConfNames = ["b"]
        seed.exerciseWorkloadSignature = ExerciseGuidanceState.workloadSignature

        names, source = ExerciseGuidanceState.choose_candidate_names(["a", "b"], seed=seed)

        self.assertEqual(["b"], names)
        self.assertEqual("seed-local", source)

    def test_choose_candidate_names_uses_project_global_when_seed_local_missing(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        ExerciseGuidanceState.configure_from_current()
        ExerciseGuidanceState.projectGlobalExercisedParams = {"b"}

        with mock.patch("utils.ExerciseGuidanceState.random.random", return_value=0.9):
            names, source = ExerciseGuidanceState.choose_candidate_names(["a", "b", "c"])

        self.assertEqual(["b"], names)
        self.assertEqual("project-global", source)

    def test_choose_candidate_names_can_explore_parsed_only(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        Configuration.fuzzerConf["exercise_guided_explore_ratio"] = "1.0"
        ExerciseGuidanceState.configure_from_current()
        ExerciseGuidanceState.projectGlobalExercisedParams = {"b"}

        with mock.patch("utils.ExerciseGuidanceState.random.random", return_value=0.0):
            names, source = ExerciseGuidanceState.choose_candidate_names(["a", "b", "c"])

        self.assertEqual(["a", "c"], names)
        self.assertEqual("exploration", source)

    def test_record_system_run_updates_global_and_accepted_sets(self):
        new_global, new_accepted = ExerciseGuidanceState.record_system_run(["a", "b"], accepted=True)

        self.assertEqual({"a", "b"}, new_global)
        self.assertEqual({"a", "b"}, new_accepted)
        self.assertEqual({"a", "b"}, ExerciseGuidanceState.projectGlobalExercisedParams)
        self.assertEqual({"a", "b"}, ExerciseGuidanceState.projectAcceptedExercisedParams)


if __name__ == "__main__":
    unittest.main()
