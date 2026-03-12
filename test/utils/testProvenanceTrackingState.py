import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from utils.Configuration import Configuration
from utils.ProvenanceTrackingState import ProvenanceTrackingState


class TestProvenanceTrackingState(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})

    def setUp(self) -> None:
        Configuration.fuzzerConf["use_provenance_agent"] = "False"
        ProvenanceTrackingState.configure_from_current()

    def test_configure_reflects_current_flag(self):
        self.assertFalse(ProvenanceTrackingState.is_enabled())
        Configuration.fuzzerConf["use_provenance_agent"] = "True"
        ProvenanceTrackingState.configure_from_current()
        self.assertTrue(ProvenanceTrackingState.is_enabled())

    def test_record_system_run_updates_global_and_bootstrap_sets(self):
        new_global, new_accepted = ProvenanceTrackingState.record_system_run(
            ["a", "b"],
            accepted=True,
            bootstrap=True,
        )

        self.assertEqual({"a", "b"}, new_global)
        self.assertEqual({"a", "b"}, new_accepted)
        self.assertEqual({"a", "b"}, ProvenanceTrackingState.projectGlobalUseBackedParams)
        self.assertEqual({"a", "b"}, ProvenanceTrackingState.projectAcceptedUseBackedParams)
        self.assertEqual({"a", "b"}, ProvenanceTrackingState.bootstrapUseBackedParams)


if __name__ == "__main__":
    unittest.main()
