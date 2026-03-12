import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from testValidator.SystemTester import SystemTester
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState


class TestSystemTesterTrackingEnv(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})

    def setUp(self) -> None:
        Configuration.fuzzerConf["exercise_guided_mutation"] = "False"
        Configuration.fuzzerConf["use_provenance_agent"] = "False"
        Configuration.fuzzerConf["provenance_agent_mode"] = "active"
        ExerciseGuidanceState.configure_from_current()

    def test_system_tracking_env_is_always_enabled_and_guidance_flag_reflects_mode(self):
        env = SystemTester()._build_system_env()
        self.assertEqual("true", env["ECFUZZ_COLLECT_EXERCISED_PARAMS"])
        self.assertEqual("false", env["ECFUZZ_EXERCISE_GUIDED_MUTATION"])
        self.assertNotIn("ECFUZZ_USE_PROVENANCE_AGENT", env)
        self.assertNotIn("-javaagent:", env.get("JAVA_TOOL_OPTIONS", ""))

        Configuration.fuzzerConf["exercise_guided_mutation"] = "True"
        ExerciseGuidanceState.configure_from_current()
        env = SystemTester()._build_system_env()
        self.assertEqual("true", env["ECFUZZ_COLLECT_EXERCISED_PARAMS"])
        self.assertEqual("true", env["ECFUZZ_EXERCISE_GUIDED_MUTATION"])

    def test_provenance_agent_env_is_injected_once(self):
        Configuration.fuzzerConf["project"] = "hadoop-common"
        Configuration.fuzzerConf["use_provenance_agent"] = "True"
        Configuration.fuzzerConf["provenance_agent_mode"] = "active"

        tester = SystemTester()
        env = tester._build_system_env()

        self.assertEqual("true", env["ECFUZZ_USE_PROVENANCE_AGENT"])
        self.assertEqual("active", env["ECFUZZ_PROVENANCE_AGENT_MODE"])
        self.assertEqual(1, env["HADOOP_OPTS"].count("-javaagent:"))
        self.assertEqual(1, env["HADOOP_CLIENT_OPTS"].count("-javaagent:"))
        self.assertEqual(1, env["HADOOP_NAMENODE_OPTS"].count("-javaagent:"))
        self.assertNotIn("JAVA_TOOL_OPTIONS", env)
        self.assertEqual(1, tester._build_system_java_command().count("-javaagent:"))


if __name__ == "__main__":
    unittest.main()
