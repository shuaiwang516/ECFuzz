from abc import ABCMeta, abstractmethod
import random
from dataModel.Seed import Seed
from dataModel.Testcase import Testcase
from utils.ExerciseGuidanceState import ExerciseGuidanceState

class Mutator(object, metaclass=ABCMeta):

    def __init__(self) -> None:
        pass

    def get_candidate_indices(self, seed: Seed):
        candidate_names, source = ExerciseGuidanceState.choose_candidate_names(
            [conf.name for conf in seed.confItemList],
            seed=seed,
        )
        candidate_name_set = set(candidate_names)
        candidate_indices = [
            index for index, conf in enumerate(seed.confItemList)
            if conf.name in candidate_name_set
        ]
        if not candidate_indices:
            candidate_indices = list(range(0, len(seed.confItemList)))
            source = "parsed-fallback" if ExerciseGuidanceState.is_enabled() else "baseline"
        return candidate_indices, source

    def choose_candidate_index(self, seed: Seed):
        candidate_indices, source = self.get_candidate_indices(seed)
        return random.choice(candidate_indices), source

    @abstractmethod
    def mutate(self, seed: Seed) -> Testcase:
        """
        Perform some mutation on the configuration items of a seed, so as to generate a testcase.

        Args:
            seed (Seed): a seed needed to be mutated.
            constraint (Constraint): a map that guides how to perform mutation.

        Returns:
            testcase (Testcase): a new testcase.
        """
        pass
