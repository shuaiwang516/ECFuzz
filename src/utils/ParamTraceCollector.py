import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from dataModel.TestResult import TestResult
from dataModel.Testcase import Testcase
from utils.Configuration import Configuration
from utils.Logger import getLogger
from utils.UnitConstant import FUZZER_DIR


class ParamTraceCollector(object):
    EVENT_PATTERN = re.compile(r"\[CTEST\]\[([A-Z0-9-]+)\]\s*(.*)")
    RAW_EXERCISED_OPERATIONS = {"GET-PARAM", "SET-PARAM", "EXERCISED-PARAM"}
    USE_BACKED_OPERATION = "USE-BACKED-EXERCISED"

    def __init__(self) -> None:
        self.logger = getLogger()
        self.project = Configuration.fuzzerConf["project"]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.runId = f"{timestamp}-{os.getpid()}"
        self.runDir = os.path.join(FUZZER_DIR, "param_tracking", self.project, self.runId)
        os.makedirs(self.runDir, exist_ok=True)
        self.summaryPath = os.path.join(self.runDir, "summary.tsv")
        with open(self.summaryPath, "w", encoding="utf-8") as fd:
            fd.write(
                "testcase_id\tunit_status\tsystem_status\tunit_tests\tunit_events\t"
                "system_events\tsystem_provenance_events\tunit_unique_params\tsystem_unique_params\t"
                "system_use_backed_unique_params\t"
                "unique_params\tparams\n"
            )

    @classmethod
    def _parse_payload(cls, payload: str) -> Tuple[str, str]:
        payload = payload.strip()
        if payload.startswith("name="):
            body = payload[len("name="):]
            if "\tstack=" in body:
                name_part, stacktrace = body.split("\tstack=", 1)
                return name_part.strip(), stacktrace.strip()
            if " stack=" in body:
                name_part, stacktrace = body.split(" stack=", 1)
                return name_part.strip(), stacktrace.strip()
            name_parts = body.split(None, 1)
            if len(name_parts) == 1:
                return name_parts[0].strip(), ""
            return name_parts[0].strip(), name_parts[1].strip()
        parts = payload.split(None, 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0].strip(), parts[1].strip()

    @classmethod
    def parse_events_from_text(
        cls,
        text: str,
        source: str,
        extra: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        if not text:
            return events

        for index, line in enumerate(text.splitlines(), 1):
            match = cls.EVENT_PATTERN.search(line)
            if not match:
                continue
            op, payload = match.groups()
            if op in cls.RAW_EXERCISED_OPERATIONS:
                op = op.replace("-PARAM", "")
            param_name, stacktrace = cls._parse_payload(payload)
            event = {
                "operation": op,
                "param_name": param_name,
                "stacktrace": stacktrace,
                "source": source,
                "raw_line": line.strip(),
                "line_number": str(index),
            }
            if extra:
                event.update(extra)
            events.append(event)
        return events

    @classmethod
    def extract_events_from_surefire(
        cls,
        surefire_locations: Sequence[str],
        clsname: str,
        expected_methods: Iterable[str],
    ) -> Tuple[Set[str], List[Dict[str, str]]]:
        expected_methods = set(expected_methods)
        report_path = None
        for surefire_path in surefire_locations:
            candidate = os.path.join(surefire_path, f"TEST-{clsname}.xml")
            if os.path.exists(candidate):
                report_path = candidate
        if report_path is None:
            return set(), []

        observed_tests: Set[str] = set()
        events: List[Dict[str, str]] = []

        try:
            tree = ET.parse(report_path)
            root = tree.getroot()
        except Exception:
            return observed_tests, events

        for testcase in root.iter(tag="testcase"):
            method_name = testcase.attrib.get("name", "")
            if method_name not in expected_methods:
                continue
            test_name = f"{clsname}#{method_name}"
            observed_tests.add(test_name)
            texts = []
            for tag in ("system-out", "system-err"):
                for node in testcase.iter(tag=tag):
                    if node.text:
                        texts.append(node.text)
            for event in cls.parse_events_from_text(
                "\n".join(texts),
                source="unit",
                extra={"unit_test": test_name, "report_path": report_path},
            ):
                events.append(event)

        if events:
            return observed_tests, events

        suite_texts = []
        for tag in ("system-out", "system-err"):
            for node in root.findall(tag):
                if node.text:
                    suite_texts.append(node.text)
        suite_source = "unit-suite" if suite_texts else "unit"
        return observed_tests, cls.parse_events_from_text(
            "\n".join(suite_texts),
            source=suite_source,
            extra={"unit_test": clsname, "report_path": report_path},
        )

    @classmethod
    def extract_events_from_log_dir(cls, log_dir: str) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        if not os.path.exists(log_dir):
            return events

        for root, _, files in os.walk(log_dir):
            for filename in files:
                log_path = os.path.join(root, filename)
                if not os.path.isfile(log_path):
                    continue
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as fd:
                        events.extend(
                            cls.parse_events_from_text(
                                fd.read(),
                                source="system-log",
                                extra={"log_path": log_path},
                            )
                        )
                except Exception:
                    continue
        return events

    @classmethod
    def snapshot_file_state(cls, root_dir: str) -> Dict[str, Tuple[int, int]]:
        state: Dict[str, Tuple[int, int]] = {}
        if not root_dir or not os.path.exists(root_dir):
            return state

        for root, _, files in os.walk(root_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                if not os.path.isfile(file_path):
                    continue
                try:
                    file_stat = os.stat(file_path)
                except OSError:
                    continue
                state[file_path] = (file_stat.st_size, file_stat.st_mtime_ns)
        return state

    @classmethod
    def extract_events_from_updated_files(
        cls,
        root_dir: str,
        previous_state: Optional[Dict[str, Tuple[int, int]]] = None,
        source: str = "system-artifact",
    ) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        if not root_dir or not os.path.exists(root_dir):
            return events

        previous_state = previous_state or {}

        for root, _, files in os.walk(root_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                if not os.path.isfile(file_path):
                    continue

                try:
                    file_stat = os.stat(file_path)
                except OSError:
                    continue

                old_state = previous_state.get(file_path)
                current_state = (file_stat.st_size, file_stat.st_mtime_ns)
                if old_state == current_state:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fd:
                        if old_state and file_stat.st_size >= old_state[0]:
                            fd.seek(old_state[0])
                        content = fd.read()
                except Exception:
                    continue

                if not content:
                    continue

                events.extend(
                    cls.parse_events_from_text(
                        content,
                        source=source,
                        extra={"log_path": file_path},
                    )
                )
        return events

    @staticmethod
    def _status(result: Optional[TestResult]) -> str:
        return "" if result is None else str(result.status)

    @staticmethod
    def _unique_params(events: List[Dict[str, str]], operations: Optional[Set[str]] = None) -> List[str]:
        return sorted(
            {
                event["param_name"]
                for event in events
                if event.get("param_name")
                and (operations is None or event.get("operation") in operations)
            }
        )

    @classmethod
    def extract_exercised_names(cls, events: List[Dict[str, str]]) -> List[str]:
        return cls._unique_params(events, operations={"GET", "SET", "EXERCISED"})

    @classmethod
    def extract_use_backed_names(cls, events: List[Dict[str, str]]) -> List[str]:
        return cls._unique_params(events, operations={cls.USE_BACKED_OPERATION})

    @classmethod
    def extract_provenance_events(cls, events: List[Dict[str, str]]) -> List[Dict[str, str]]:
        return [
            event
            for event in events
            if event.get("operation", "").startswith("PROV-")
            or event.get("operation") == cls.USE_BACKED_OPERATION
        ]

    def record_testcase(
        self,
        testcase: Testcase,
        unit_tests: Iterable[str],
        unit_events: List[Dict[str, str]],
        system_events: List[Dict[str, str]],
        unit_result: Optional[TestResult],
        system_result: Optional[TestResult],
    ) -> str:
        testcase_id = testcase.fileName if testcase.fileName else os.path.basename(testcase.filePath)
        testcase_params = {item.name: item.value for item in testcase.confItemList}
        all_events = list(unit_events) + list(system_events)
        unit_unique_params = self._unique_params(unit_events, operations={"GET", "SET", "EXERCISED"})
        system_unique_params = self._unique_params(system_events, operations={"GET", "SET", "EXERCISED"})
        system_use_backed_unique_params = self._unique_params(
            system_events,
            operations={self.USE_BACKED_OPERATION},
        )
        unique_params = self._unique_params(all_events, operations={"GET", "SET", "EXERCISED"})
        system_provenance_events = self.extract_provenance_events(system_events)

        record = {
            "project": self.project,
            "run_id": self.runId,
            "testcase_id": testcase_id,
            "testcase_path": testcase.filePath,
            "testcase_params": testcase_params,
            "mutated_params": list(getattr(testcase, "mutatedConfNames", [])),
            "mutation_before_values": dict(getattr(testcase, "mutationBeforeValues", {})),
            "mutation_after_values": dict(getattr(testcase, "mutationAfterValues", {})),
            "mutation_candidate_source": getattr(testcase, "mutationCandidateSource", "baseline"),
            "system_exercised_params": list(getattr(testcase, "systemExercisedConfNames", [])),
            "system_use_backed_exercised_params": list(
                getattr(testcase, "systemUseBackedExercisedConfNames", [])
            ),
            "system_exercise_workload_signature": getattr(testcase, "systemExerciseWorkloadSignature", ""),
            "unit_tests": sorted(set(unit_tests)),
            "unit_status": self._status(unit_result),
            "system_status": self._status(system_result),
            "counts": {
                "unit_tests": len(set(unit_tests)),
                "unit_events": len(unit_events),
                "system_events": len(system_events),
                "system_provenance_events": len(system_provenance_events),
                "unit_unique_params": len(unit_unique_params),
                "system_unique_params": len(system_unique_params),
                "system_use_backed_unique_params": len(system_use_backed_unique_params),
                "raw_vs_use_backed_gap": len(system_unique_params) - len(system_use_backed_unique_params),
                "unique_params": len(unique_params),
            },
            "unique_params": unique_params,
            "unit_unique_params": unit_unique_params,
            "system_unique_params": system_unique_params,
            "system_use_backed_unique_params": system_use_backed_unique_params,
            "unit_events": unit_events,
            "system_events": system_events,
            "system_provenance_events": system_provenance_events,
        }

        output_path = os.path.join(self.runDir, f"{testcase_id}.json")
        with open(output_path, "w", encoding="utf-8") as fd:
            json.dump(record, fd, indent=2, sort_keys=True)

        with open(self.summaryPath, "a", encoding="utf-8") as fd:
            fd.write(
                f"{testcase_id}\t{record['unit_status']}\t{record['system_status']}\t"
                f"{record['counts']['unit_tests']}\t{record['counts']['unit_events']}\t"
                f"{record['counts']['system_events']}\t{record['counts']['system_provenance_events']}\t"
                f"{record['counts']['unit_unique_params']}\t{record['counts']['system_unique_params']}\t"
                f"{record['counts']['system_use_backed_unique_params']}\t{record['counts']['unique_params']}\t"
                f"{','.join(unique_params)}\n"
            )
        self.logger.info(
            f">>>>[ParamTraceCollector] recorded {testcase_id} with "
            f"{record['counts']['unique_params']} exercised params"
        )
        return output_path
