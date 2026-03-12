import random
from typing import Iterable, List, Sequence, Set, Tuple

from utils.Configuration import Configuration
from utils.Logger import getLogger


class ExerciseGuidanceState(object):
    logger = getLogger()

    exerciseGuidedMutation: bool = False
    exploreRatio: float = 0.10
    projectGlobalExercisedParams: Set[str] = set()
    projectAcceptedExercisedParams: Set[str] = set()
    bootstrapComplete: bool = False
    bootstrapRan: bool = False
    bootstrapSourceTestcase: str = ""
    bootstrapExercisedParams: Set[str] = set()
    workloadSignature: str = ""
    nonzeroSystemRuns: int = 0
    nonzeroAcceptedSystemRuns: int = 0

    @classmethod
    def reset_runtime_state(cls) -> None:
        cls.projectGlobalExercisedParams = set()
        cls.projectAcceptedExercisedParams = set()
        cls.bootstrapComplete = False
        cls.bootstrapRan = False
        cls.bootstrapSourceTestcase = ""
        cls.bootstrapExercisedParams = set()
        cls.nonzeroSystemRuns = 0
        cls.nonzeroAcceptedSystemRuns = 0
        cls.workloadSignature = cls.current_workload_signature()

    @classmethod
    def configure_from_current(cls) -> None:
        conf = Configuration.fuzzerConf
        cls.exerciseGuidedMutation = conf.get("exercise_guided_mutation", "False") == "True"
        try:
            cls.exploreRatio = float(conf.get("exercise_guided_explore_ratio", "0.10"))
        except (TypeError, ValueError):
            cls.exploreRatio = 0.10
        cls.exploreRatio = max(0.0, min(1.0, cls.exploreRatio))
        cls.reset_runtime_state()

    @classmethod
    def is_enabled(cls) -> bool:
        return cls.exerciseGuidedMutation

    @classmethod
    def current_workload_signature(cls) -> str:
        project = Configuration.fuzzerConf.get("project", "")
        tester = Configuration.fuzzerConf.get("systemtester", "")
        shell = Configuration.putConf.get("systest_shell", "") if hasattr(Configuration, "putConf") else ""
        return "|".join([project, tester, shell])

    @classmethod
    def should_run_bootstrap(cls) -> bool:
        return cls.is_enabled() and cls.bootstrapComplete is False

    @classmethod
    def mark_bootstrap(cls, testcase_id: str, exercised_names: Iterable[str]) -> None:
        exercised_set = {name for name in exercised_names if name}
        cls.bootstrapComplete = True
        cls.bootstrapRan = True
        cls.bootstrapSourceTestcase = testcase_id
        cls.bootstrapExercisedParams = exercised_set
        cls.record_system_run(exercised_set, accepted=True, bootstrap=True)

    @classmethod
    def record_system_run(
        cls,
        exercised_names: Iterable[str],
        accepted: bool,
        bootstrap: bool = False,
    ) -> Tuple[Set[str], Set[str]]:
        exercised_set = {name for name in exercised_names if name}
        if exercised_set:
            cls.nonzeroSystemRuns += 1
        new_global = exercised_set.difference(cls.projectGlobalExercisedParams)
        cls.projectGlobalExercisedParams.update(exercised_set)

        new_accepted: Set[str] = set()
        if accepted or bootstrap:
            if exercised_set:
                cls.nonzeroAcceptedSystemRuns += 1
            new_accepted = exercised_set.difference(cls.projectAcceptedExercisedParams)
            cls.projectAcceptedExercisedParams.update(exercised_set)
        return new_global, new_accepted

    @classmethod
    def get_project_candidate_params(cls) -> Set[str]:
        if cls.projectAcceptedExercisedParams:
            return set(cls.projectAcceptedExercisedParams)
        return set(cls.projectGlobalExercisedParams)

    @classmethod
    def workload_matches_seed(cls, seed) -> bool:
        seed_signature = getattr(seed, "exerciseWorkloadSignature", "")
        return seed_signature != "" and seed_signature == cls.workloadSignature

    @classmethod
    def choose_candidate_names(
        cls,
        available_names: Sequence[str],
        seed=None,
    ) -> Tuple[List[str], str]:
        deduped_available = list(dict.fromkeys(name for name in available_names if name))
        if not deduped_available:
            return [], "parsed-fallback"
        if not cls.is_enabled():
            return deduped_available, "baseline"

        project_params = cls.get_project_candidate_params()
        unexplored = [name for name in deduped_available if name not in project_params]
        if unexplored and random.random() < cls.exploreRatio:
            return unexplored, "exploration"

        if seed is not None and cls.workload_matches_seed(seed):
            seed_params = set(getattr(seed, "lastExercisedConfNames", []))
            seed_candidates = [name for name in deduped_available if name in seed_params]
            if seed_candidates:
                return seed_candidates, "seed-local"

        if project_params:
            project_candidates = [name for name in deduped_available if name in project_params]
            if project_candidates:
                return project_candidates, "project-global"

        return deduped_available, "parsed-fallback"
