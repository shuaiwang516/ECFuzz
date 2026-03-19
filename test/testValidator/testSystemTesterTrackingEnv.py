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

    def test_alluxio_uses_only_shared_java_opts_for_provenance_agent(self):
        Configuration.fuzzerConf["project"] = "alluxio"
        Configuration.fuzzerConf["use_provenance_agent"] = "True"
        Configuration.fuzzerConf["provenance_agent_mode"] = "active"

        env = SystemTester()._build_system_env()

        self.assertEqual("true", env["ECFUZZ_USE_PROVENANCE_AGENT"])
        self.assertEqual(1, env["ALLUXIO_AGENT_JAVA_OPTS"].count("-javaagent:"))
        self.assertNotIn("ALLUXIO_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_MASTER_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_WORKER_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_JOB_MASTER_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_JOB_WORKER_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_PROXY_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_LOGSERVER_JAVA_OPTS", env)
        self.assertNotIn("ALLUXIO_USER_JAVA_OPTS", env)

    def test_trace_diagnostics_distinguish_zero_row_cases(self):
        tester = SystemTester()

        status, details = tester._summarize_trace_run("", "", [], [], [])
        self.assertEqual("system-run-no-trace-sources", status)
        self.assertEqual([], details["trace_input_sources"])

        log_sources = [
            {
                "source": "system-log",
                "path": "/tmp/logs/namenode.log",
                "relative_path": "namenode.log",
                "content": "INFO namenode started\n",
            }
        ]
        status, details = tester._summarize_trace_run("", "", log_sources, [], [])
        self.assertEqual("system-run-trace-sources-zero-extracted-params", status)
        self.assertEqual(["log-files"], details["trace_input_sources"])
        self.assertEqual(1, details["updated_log_file_count"])

        system_events = [
            {
                "operation": "GET",
                "param_name": "dfs.replication",
                "source": "system-log",
                "log_path": "/tmp/logs/namenode.log",
            }
        ]
        status, details = tester._summarize_trace_run("", "", log_sources, [], system_events)
        self.assertEqual("system-run-trace-sources-nonzero-extracted-params", status)
        self.assertEqual(1, details["system_exercised_unique_param_count"])
        self.assertEqual(["system-log"], details["system_exercised_event_sources"])


if __name__ == "__main__":
    unittest.main()
