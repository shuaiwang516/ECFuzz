import importlib
import json
import os
import tempfile
import time
import unittest
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from dataModel.TestResult import TestResult
from dataModel.Testcase import Testcase
from utils.Configuration import Configuration
from utils.ParamTraceCollector import ParamTraceCollector


class TestParamTraceCollector(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Configuration.parseConfiguration({})

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
                source="system-log",
            )

            self.assertEqual(1, len(events))
            self.assertEqual("dfs.replication", events[0]["param_name"])
            self.assertEqual("system-log", events[0]["source"])
            self.assertEqual(artifact_path, events[0]["log_path"])

    def test_collect_updated_text_sources_reads_full_system_shell_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = os.path.join(tmpdir, "start_hdfs")
            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write("[CTEST][EXERCISED-PARAM] name=old.value\n")

            snapshot = ParamTraceCollector.snapshot_file_state(tmpdir)
            time.sleep(0.01)

            rewritten_content = "\n".join(
                [
                    "[CTEST][EXERCISED-PARAM] name=new.value",
                    "[CTEST][EXERCISED-PARAM] name=tail.value",
                    "",
                ]
            )
            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write(rewritten_content)

            text_sources = ParamTraceCollector.collect_updated_text_sources(
                tmpdir,
                snapshot,
                source="system-shell",
            )

            self.assertEqual(1, len(text_sources))
            self.assertEqual(rewritten_content, text_sources[0]["content"])
            self.assertEqual("start_hdfs", text_sources[0]["relative_path"])

    def test_collect_updated_text_sources_keeps_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "nested"), exist_ok=True)
            artifact_path = os.path.join(tmpdir, "nested", "namenode.log")
            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write("before-run\n")

            snapshot = ParamTraceCollector.snapshot_file_state(tmpdir)

            with open(artifact_path, "a", encoding="utf-8") as fd:
                fd.write("INFO shell output\n")

            text_sources = ParamTraceCollector.collect_updated_text_sources(
                tmpdir,
                snapshot,
                source="system-log",
            )

            self.assertEqual(1, len(text_sources))
            self.assertEqual("system-log", text_sources[0]["source"])
            self.assertEqual("nested/namenode.log", text_sources[0]["relative_path"])
            self.assertEqual(artifact_path, text_sources[0]["path"])
            self.assertIn("INFO shell output", text_sources[0]["content"])

    def test_collect_updated_text_sources_falls_back_to_full_rewritten_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = os.path.join(tmpdir, "hdfs_safety")
            original_content = "1234567890\nabcdefghij\n"
            rewritten_content = "abcdefghij\n1234567890\n"

            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write(original_content)

            snapshot = ParamTraceCollector.snapshot_file_state(tmpdir)
            time.sleep(0.01)

            with open(artifact_path, "w", encoding="utf-8") as fd:
                fd.write(rewritten_content)

            text_sources = ParamTraceCollector.collect_updated_text_sources(
                tmpdir,
                snapshot,
                source="system-shell",
            )

            self.assertEqual(1, len(text_sources))
            self.assertEqual(rewritten_content, text_sources[0]["content"])
            self.assertEqual("hdfs_safety", text_sources[0]["relative_path"])

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

    def test_record_testcase_preserves_trace_artifacts_and_status(self):
        module = importlib.import_module("utils.ParamTraceCollector")
        old_fuzzer_dir = module.FUZZER_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            module.FUZZER_DIR = tmpdir
            try:
                collector = module.ParamTraceCollector()
                testcase = Testcase([])
                testcase.fileName = "Testcase-1"
                testcase.filePath = "/tmp/Testcase-1.xml"
                testcase.systemTraceStatus = "system-run-trace-sources-zero-extracted-params"
                testcase.systemTraceDetails = {"trace_input_sources": ["stdout", "log-files", "shell-files"]}

                output_path = collector.record_testcase(
                    testcase,
                    unit_tests=[],
                    unit_events=[],
                    system_events=[],
                    unit_result=TestResult(status=0),
                    system_result=TestResult(status=0),
                    system_trace_capture={
                        "stdout_text": "system stdout\n",
                        "stderr_text": "",
                        "log_sources": [
                            {
                                "source": "system-log",
                                "path": "/tmp/logs/hdfs.log",
                                "relative_path": "namenode/hdfs.log",
                                "content": "INFO namenode start\n",
                            }
                        ],
                        "shell_sources": [
                            {
                                "source": "system-shell",
                                "path": "/tmp/shell/start_hdfs",
                                "relative_path": "start_hdfs",
                                "content": "shell output\n",
                            }
                        ],
                    },
                )

                with open(output_path, "r", encoding="utf-8") as fd:
                    payload = json.load(fd)

                self.assertEqual(
                    "system-run-trace-sources-zero-extracted-params",
                    payload["system_trace_status"],
                )
                self.assertEqual(["stdout", "log-files", "shell-files"], payload["system_trace_input_sources"])
                self.assertEqual(3, len(payload["system_trace_artifacts"]))
                self.assertTrue(os.path.isdir(payload["system_trace_artifact_dir"]))
                for artifact in payload["system_trace_artifacts"]:
                    self.assertTrue(os.path.exists(artifact["artifact_path"]))

                with open(collector.summaryPath, "r", encoding="utf-8") as fd:
                    rows = fd.read().splitlines()
                header = rows[0].split("\t")
                row = rows[1].split("\t")
                row_map = dict(zip(header, row))
                self.assertEqual(
                    "system-run-trace-sources-zero-extracted-params",
                    row_map["system_trace_status"],
                )
                self.assertEqual("stdout,log-files,shell-files", row_map["system_trace_input_sources"])
                self.assertEqual("3", row_map["system_trace_artifact_count"])
            finally:
                module.FUZZER_DIR = old_fuzzer_dir


if __name__ == "__main__":
    unittest.main()
