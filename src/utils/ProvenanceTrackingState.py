from typing import Iterable, Set, Tuple

from utils.Configuration import Configuration


class ProvenanceTrackingState(object):
    useProvenanceAgent: bool = False
    projectGlobalUseBackedParams: Set[str] = set()
    projectAcceptedUseBackedParams: Set[str] = set()
    bootstrapUseBackedParams: Set[str] = set()
    nonzeroUseBackedSystemRuns: int = 0
    nonzeroUseBackedAcceptedSystemRuns: int = 0

    @classmethod
    def reset_runtime_state(cls) -> None:
        cls.projectGlobalUseBackedParams = set()
        cls.projectAcceptedUseBackedParams = set()
        cls.bootstrapUseBackedParams = set()
        cls.nonzeroUseBackedSystemRuns = 0
        cls.nonzeroUseBackedAcceptedSystemRuns = 0

    @classmethod
    def configure_from_current(cls) -> None:
        cls.useProvenanceAgent = Configuration.fuzzerConf.get("use_provenance_agent", "False") == "True"
        cls.reset_runtime_state()

    @classmethod
    def is_enabled(cls) -> bool:
        return cls.useProvenanceAgent

    @classmethod
    def record_system_run(
        cls,
        use_backed_names: Iterable[str],
        accepted: bool,
        bootstrap: bool = False,
    ) -> Tuple[Set[str], Set[str]]:
        use_backed_set = {name for name in use_backed_names if name}
        if use_backed_set:
            cls.nonzeroUseBackedSystemRuns += 1
        new_global = use_backed_set.difference(cls.projectGlobalUseBackedParams)
        cls.projectGlobalUseBackedParams.update(use_backed_set)

        new_accepted: Set[str] = set()
        if accepted or bootstrap:
            if use_backed_set:
                cls.nonzeroUseBackedAcceptedSystemRuns += 1
            new_accepted = use_backed_set.difference(cls.projectAcceptedUseBackedParams)
            cls.projectAcceptedUseBackedParams.update(use_backed_set)
        if bootstrap:
            cls.bootstrapUseBackedParams = set(use_backed_set)
        return new_global, new_accepted
