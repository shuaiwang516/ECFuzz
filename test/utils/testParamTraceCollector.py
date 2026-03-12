import os
import tempfile
import unittest
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from utils.ParamTraceCollector import ParamTraceCollector


class TestParamTraceCollector(unittest.TestCase):
    def test_parse_events_from_text_supports_legacy_and_structured_lines(self):
        text = "\n".join(
            [
                "[CTEST][GET-PARAM] name=fs.defaultFS\tstack=Caller#method:1\tNext#call:2",
                "2024-01-01 WARN [CTEST][SET-PARAM] dfs.replication org.apache.hadoop.A\torg.apache.hadoop.B",
                "[CTEST][GET-PARAM] clientPort",
            ]
        )

        events = ParamTraceCollector.parse_events_from_text(text, source="unit")

        self.assertEqual(3, len(events))
        self.assertEqual("GET", events[0]["operation"])
        self.assertEqual("fs.defaultFS", events[0]["param_name"])
        self.assertIn("Caller#method:1", events[0]["stacktrace"])
        self.assertEqual("SET", events[1]["operation"])
        self.assertEqual("dfs.replication", events[1]["param_name"])
        self.assertIn("org.apache.hadoop.A", events[1]["stacktrace"])
        self.assertEqual("clientPort", events[2]["param_name"])
        self.assertEqual("", events[2]["stacktrace"])

    def test_extract_events_from_surefire_reads_system_out(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = os.path.join(tmpdir, "TEST-org.example.TestConfig.xml")
            with open(report_path, "w", encoding="utf-8") as fd:
                fd.write(
                    """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="1" errors="0" failures="0">
  <testcase classname="org.example.TestConfig" name="testRead" time="0.1">
    <system-out><![CDATA[[CTEST][GET-PARAM] name=my.key\tstack=Example#call:1]]></system-out>
  </testcase>
</testsuite>
"""
                )

            observed, events = ParamTraceCollector.extract_events_from_surefire(
                [tmpdir],
                "org.example.TestConfig",
                {"testRead"},
            )

            self.assertEqual({"org.example.TestConfig#testRead"}, observed)
            self.assertEqual(1, len(events))
            self.assertEqual("my.key", events[0]["param_name"])
            self.assertEqual("org.example.TestConfig#testRead", events[0]["unit_test"])

    def test_extract_events_from_updated_files_only_reads_new_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = os.path.join(tmpdir, "start_hdfs")
            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write("before-run\n")

            snapshot = ParamTraceCollector.snapshot_file_state(tmpdir)

            with open(artifact_path, "a", encoding="utf-8") as fd:
                fd.write("[CTEST][GET-PARAM] name=dfs.replication\tstack=Caller#read:1\n")

            events = ParamTraceCollector.extract_events_from_updated_files(
                tmpdir,
                snapshot,
                source="system-shell",
            )

            self.assertEqual(1, len(events))
            self.assertEqual("dfs.replication", events[0]["param_name"])
            self.assertEqual("system-shell", events[0]["source"])
            self.assertEqual(artifact_path, events[0]["log_path"])

    def test_parse_exercised_param_marker(self):
        text = "[CTEST][EXERCISED-PARAM] name=dfs.blocksize"

        events = ParamTraceCollector.parse_events_from_text(text, source="system")

        self.assertEqual(1, len(events))
        self.assertEqual("EXERCISED", events[0]["operation"])
        self.assertEqual("dfs.blocksize", events[0]["param_name"])

    def test_parse_use_backed_and_provenance_markers(self):
        text = "\n".join(
            [
                "[CTEST][USE-BACKED-EXERCISED] name=dfs.replication reason=field-touch site=Example#read",
                "[CTEST][PROV-FIELD-STORE] name=dfs.replication field=Example#field writer=Example#write",
            ]
        )

        events = ParamTraceCollector.parse_events_from_text(text, source="system")

        self.assertEqual(2, len(events))
        self.assertEqual("USE-BACKED-EXERCISED", events[0]["operation"])
        self.assertEqual("dfs.replication", events[0]["param_name"])
        self.assertEqual(["dfs.replication"], ParamTraceCollector.extract_use_backed_names(events))
        self.assertEqual(2, len(ParamTraceCollector.extract_provenance_events(events)))


if __name__ == "__main__":
    unittest.main()
