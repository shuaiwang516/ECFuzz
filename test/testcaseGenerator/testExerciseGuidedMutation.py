import os
import random
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from dataModel.ConfItem import ConfItem
from dataModel.Seed import Seed
from seedGenerator.SeedGenerator import SeedGenerator
from testcaseGenerator.SingleMutator import SingleMutator
from testcaseGenerator.SmartMutator import SmartMutator
from utils.ConfAnalyzer import ConfAnalyzer
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.ShowStats import ShowStats


class TestExerciseGuidedMutation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})
        ConfAnalyzer.analyzeConfItems()

    def setUp(self) -> None:
        Configuration.fuzzerConf["exercise_guided_mutation"] = "False"
        Configuration.fuzzerConf["exercise_guided_explore_ratio"] = "0.10"
        ExerciseGuidanceState.configure_from_current()
        ShowStats.stackMutationFlag = 0

    def test_single_mutator_uses_project_global_candidate_when_enabled(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        ExerciseGuidanceState.configure_from_current()
        ExerciseGuidanceState.projectGlobalExercisedParams = {"b"}
        seed = Seed(
            [
                ConfItem("a", "INT", "1"),
                ConfItem("b", "INT", "2"),
                ConfItem("c", "INT", "3"),
            ]
        )

        testcase = SingleMutator().mutate(seed)

        self.assertEqual("project-global", testcase.mutationCandidateSource)
        self.assertEqual(["b"], testcase.mutatedConfNames)

    def test_smart_mutator_uses_seed_local_candidate_when_enabled(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        ExerciseGuidanceState.configure_from_current()
        seed = Seed(
            [
                ConfItem("a", "INT", "1"),
                ConfItem("b", "INT", "2"),
                ConfItem("c", "INT", "3"),
            ]
        )
        seed.lastExercisedConfNames = ["c"]
        seed.exerciseWorkloadSignature = ExerciseGuidanceState.workloadSignature

        testcase = SmartMutator().mutate(seed)

        self.assertEqual("seed-local", testcase.mutationCandidateSource)
        self.assertEqual(["c"], testcase.mutatedConfNames)

    def test_seed_generator_uses_guided_universe_when_enabled(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        Configuration.fuzzerConf["mutator"] = "testcaseGenerator.SingleMutator.SingleMutator"
        Configuration.fuzzerConf["seed_gen_seq_ratio"] = "0"
        ExerciseGuidanceState.configure_from_current()
        ExerciseGuidanceState.projectGlobalExercisedParams = {"b"}

        sg = SeedGenerator()
        sg.confItemMutable = ["a", "b", "c"]
        sg.confItemMutableSize = len(sg.confItemMutable)
        sg.confItemsBasic = []
        sg.confItems = list(sg.confItemMutable)
        sg.confItemRelations = {}
        sg.confItemTypeMap = {"a": "INT", "b": "INT", "c": "INT"}
        sg.confItemValueMap = {"a": "1", "b": "2", "c": "3"}

        random.seed(0)
        seed = sg.generateSeed()

        self.assertEqual(["b"], [item.name for item in seed.confItemList])

    def test_seed_generator_resets_sequential_index_for_small_guided_universe(self):
        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        Configuration.fuzzerConf["mutator"] = "testcaseGenerator.SmartMutator.SmartMutator"
        Configuration.fuzzerConf["seed_gen_seq_ratio"] = "1"
        ExerciseGuidanceState.configure_from_current()
        ExerciseGuidanceState.projectGlobalExercisedParams = {"b", "c"}

        sg = SeedGenerator()
        sg.confItemMutable = ["a", "b", "c", "d"]
        sg.confItemMutableSize = len(sg.confItemMutable)
        sg.confItemsBasic = []
        sg.confItems = list(sg.confItemMutable)
        sg.confItemRelations = {}
        sg.confItemTypeMap = {"a": "INT", "b": "INT", "c": "INT", "d": "INT"}
        sg.confItemValueMap = {"a": "1", "b": "2", "c": "3", "d": "4"}
        sg.sequentialGeneratorIndex = 3

        random.seed(0)
        seed = sg.generateSeed()

        self.assertNotEqual([], [item.name for item in seed.confItemList])
        self.assertTrue(set(item.name for item in seed.confItemList).issubset({"b", "c"}))


if __name__ == "__main__":
    unittest.main()
