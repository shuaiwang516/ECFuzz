import os, shutil, time, stat
import subprocess, threading
from subprocess import Popen, PIPE, STDOUT
import shlex

from dataModel.TestResult import TestResult
from dataModel.Testcase import Testcase
from testValidator.Tester import Tester
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.Logger import getLogger
from utils.ShowStats import ShowStats
from utils.ConfAnalyzer import ConfAnalyzer
from queue import Queue
from testValidator.MonitorThread import MonitorThread
from utils.UnitConstant import DATA_DIR
from utils.ParamTraceCollector import ParamTraceCollector

class SystemTester(Tester):
    """
    System Tester perform system level testing to validate the testcase.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = getLogger()
        self.project: str = Configuration.fuzzerConf['project']
        # self.Result = TestResult()
        # init pre_find_time as fuzzer start time
        self.preFindTime: float = ShowStats.fuzzerStartTime
        self.totalTime: float = 0.0 # total time for run time
        self.totalCount: int = 0 # it equals to the testcases' number
        self.exceptionMap = {} # 
        self.exceptionMapReason = {} # 
        self.valueMap = ConfAnalyzer.confItemValueMap
        self.logLocation = {
            "hbase": os.path.join(DATA_DIR,"app_sysTest/hbase-2.2.2-work/logs"),
            "hadoop-hdfs": os.path.join(DATA_DIR, "app_sysTest/hadoop-2.8.5-work/logs"),
            "hadoop-common": os.path.join(DATA_DIR, "app_sysTest/hadoop-2.8.5-work/logs"),
            "alluxio": os.path.join(DATA_DIR, "app_sysTest/alluxio-2.1.0-work/logs"),
            "zookeeper": os.path.join(DATA_DIR, "app_sysTest/zookeeper-3.5.6-work/logs")
        }
        self._reset_trace_state()

    def _build_provenance_agent_opts(self):
        if Configuration.fuzzerConf.get("use_provenance_agent", "False") != "True":
            return ""
        project = Configuration.fuzzerConf["project"]
        mode = Configuration.fuzzerConf.get("provenance_agent_mode", "active")
        agent_jar = "/home/hadoop/ecfuzz/agent/provenance-agent/ecfuzz-provenance-agent.jar"
        allow_map = {
            "hadoop-common": "org/apache/hadoop/",
            "hadoop-hdfs": "org/apache/hadoop/",
            "hbase": "org/apache/hadoop/hbase/;org/apache/hadoop/",
            "zookeeper": "org/apache/zookeeper/",
            "alluxio": "alluxio/",
        }
        deny_map = {
            "hadoop-common": (
                "org/apache/hadoop/metrics2/;"
                "org/apache/hadoop/security/;"
                "org/apache/hadoop/ipc/CallerContext"
            ),
            "hadoop-hdfs": (
                "org/apache/hadoop/metrics2/;"
                "org/apache/hadoop/security/;"
                "org/apache/hadoop/ipc/CallerContext"
            ),
            "hbase": (
                "org/apache/hadoop/metrics2/;"
                "org/apache/hadoop/security/;"
                "org/apache/hadoop/ipc/CallerContext"
            ),
            "zookeeper": "",
            "alluxio": "",
        }
        return (
            f"-javaagent:{agent_jar}="
            f"project={project},mode={mode},emit_raw=true,emit_use_backed=true,"
            f"arg_mode=caller-pass,field_mode=true,allow={allow_map.get(project, '')},"
            f"deny={deny_map.get(project, '')}"
        )

    def replaceConfig(self, testcase: Testcase):
        srcReplacePath = testcase.filePath
        dstReplacePath = Configuration.putConf['replace_conf_path']
        shutil.copyfile(srcReplacePath, dstReplacePath)
        self.logger.info(
            f">>>>[systest] {srcReplacePath} replacement to the corresponding configuration file:{dstReplacePath}")

    def _build_system_env(self):
        env = os.environ.copy()
        env["ECFUZZ_COLLECT_EXERCISED_PARAMS"] = "true"
        env["ECFUZZ_EXERCISE_GUIDED_MUTATION"] = "true" if ExerciseGuidanceState.is_enabled() else "false"
        agent_opts = self._build_provenance_agent_opts()
        if agent_opts != "":
            project = Configuration.fuzzerConf["project"]
            mode = Configuration.fuzzerConf.get("provenance_agent_mode", "active")
            env["ECFUZZ_USE_PROVENANCE_AGENT"] = "true"
            env["ECFUZZ_PROVENANCE_AGENT_MODE"] = mode
            if project == "alluxio":
                for env_name in (
                    "ALLUXIO_JAVA_OPTS",
                    "ALLUXIO_MASTER_JAVA_OPTS",
                    "ALLUXIO_JOB_MASTER_JAVA_OPTS",
                    "ALLUXIO_WORKER_JAVA_OPTS",
                    "ALLUXIO_JOB_WORKER_JAVA_OPTS",
                    "ALLUXIO_PROXY_JAVA_OPTS",
                    "ALLUXIO_LOGSERVER_JAVA_OPTS",
                    "ALLUXIO_USER_JAVA_OPTS",
                ):
                    env.pop(env_name, None)
                env["ALLUXIO_AGENT_JAVA_OPTS"] = agent_opts
                return env
            project_opt_envs = {
                "hadoop-common": (
                    "HADOOP_OPTS",
                    "HADOOP_CLIENT_OPTS",
                    "HADOOP_NAMENODE_OPTS",
                    "HADOOP_DATANODE_OPTS",
                    "HADOOP_SECONDARYNAMENODE_OPTS",
                    "HADOOP_JOURNALNODE_OPTS",
                    "HADOOP_ZKFC_OPTS",
                ),
                "hadoop-hdfs": (
                    "HADOOP_OPTS",
                    "HADOOP_CLIENT_OPTS",
                    "HADOOP_NAMENODE_OPTS",
                    "HADOOP_DATANODE_OPTS",
                    "HADOOP_SECONDARYNAMENODE_OPTS",
                    "HADOOP_JOURNALNODE_OPTS",
                    "HADOOP_ZKFC_OPTS",
                ),
                "hbase": (
                    "HADOOP_OPTS",
                    "HADOOP_CLIENT_OPTS",
                    "HBASE_OPTS",
                    "HBASE_MASTER_OPTS",
                    "HBASE_REGIONSERVER_OPTS",
                    "HBASE_ZOOKEEPER_OPTS",
                    "HBASE_SHELL_OPTS",
                ),
                "zookeeper": ("SERVER_JVMFLAGS", "CLIENT_JVMFLAGS", "JVMFLAGS"),
            }
            for env_name in project_opt_envs.get(project, ()):
                current_value = env.get(env_name, "").strip()
                env[env_name] = agent_opts if current_value == "" else f"{agent_opts} {current_value}"
        return env

    def _build_system_java_command(self):
        sys_java = Configuration.putConf['systest_java']
        agent_opts = self._build_provenance_agent_opts()
        if agent_opts == "":
            return sys_java
        return f"{shlex.quote(sys_java)} {shlex.quote(agent_opts)}"

    def _reset_trace_state(self) -> None:
        self.lastTraceEvents = []
        self.lastExercisedConfNames = []
        self.lastUseBackedConfNames = []
        self.lastTraceStatus = "no-system-run"
        self.lastTraceDetails = {}
        self.lastTraceCapture = {}

    def _summarize_trace_run(
        self,
        stdout_text: str,
        stderr_text: str,
        log_sources,
        shell_sources,
        system_events,
    ):
        exercised_events = [
            event for event in system_events if event.get("operation") in {"GET", "SET", "EXERCISED"}
        ]
        exercised_names = ParamTraceCollector.extract_exercised_names(system_events)

        trace_input_sources = []
        if stdout_text.strip() != "":
            trace_input_sources.append("stdout")
        if stderr_text.strip() != "":
            trace_input_sources.append("stderr")
        if len(log_sources) != 0:
            trace_input_sources.append("log-files")
        if len(shell_sources) != 0:
            trace_input_sources.append("shell-files")

        if len(trace_input_sources) == 0:
            trace_status = "system-run-no-trace-sources"
        elif len(exercised_names) == 0:
            trace_status = "system-run-trace-sources-zero-extracted-params"
        else:
            trace_status = "system-run-trace-sources-nonzero-extracted-params"

        trace_details = {
            "trace_input_sources": trace_input_sources,
            "stdout_nonempty": stdout_text.strip() != "",
            "stderr_nonempty": stderr_text.strip() != "",
            "stdout_line_count": len(stdout_text.splitlines()) if stdout_text else 0,
            "stderr_line_count": len(stderr_text.splitlines()) if stderr_text else 0,
            "updated_log_files": [entry.get("path", "") for entry in log_sources],
            "updated_log_relative_paths": [entry.get("relative_path", "") for entry in log_sources],
            "updated_shell_files": [entry.get("path", "") for entry in shell_sources],
            "updated_shell_relative_paths": [entry.get("relative_path", "") for entry in shell_sources],
            "updated_log_file_count": len(log_sources),
            "updated_shell_file_count": len(shell_sources),
            "system_event_count": len(system_events),
            "system_event_sources": ParamTraceCollector.distinct_values(system_events, "source"),
            "system_event_source_counts": ParamTraceCollector.count_values(system_events, "source"),
            "system_exercised_event_count": len(exercised_events),
            "system_exercised_unique_param_count": len(exercised_names),
            "system_exercised_event_sources": ParamTraceCollector.distinct_values(exercised_events, "source"),
            "system_exercised_event_source_counts": ParamTraceCollector.count_values(
                exercised_events,
                "source",
            ),
            "system_event_log_paths": ParamTraceCollector.distinct_values(system_events, "log_path"),
            "system_exercised_event_log_paths": ParamTraceCollector.distinct_values(
                exercised_events,
                "log_path",
            ),
        }
        return trace_status, trace_details

    def runSystemTestUtils(self, testcase: Testcase, logDir: str, stopSoon: Queue, recordStats: bool = True) -> TestResult:
        Result = TestResult()
        # Result.count -= 1
        # if self.project == "alluxio":
        #     sysChmod = "echo kb310 | sudo -S chmod -R 777 /home/hadoop/ecfuzz/data/app_sysTest/alluxio-2.1.0-work/underFSStorage"
        #     process = subprocess.run(sysChmod, shell=True, stdout=PIPE, stderr=PIPE, universal_newlines=True) 
        systestShellDir = Configuration.putConf['systest_shell_dir']
        sysCmd = f"cd {systestShellDir} && {self._build_system_java_command()} {Configuration.putConf['systest_shell']}"
        self.logger.info(f">>>>[systest] {self.project} is undergoing system test validation...")
        sysStartTime = time.time()
        stop = Queue()
        threading.Thread(target=MonitorThread.threadMonitor, args=[stop, logDir, stopSoon]).start()
        logFileState = ParamTraceCollector.snapshot_file_state(logDir)
        shellFileState = ParamTraceCollector.snapshot_file_state(systestShellDir)
        process = subprocess.run(
            sysCmd,
            shell=True,
            stdout=PIPE,
            stderr=PIPE,
            universal_newlines=True,
            env=self._build_system_env(),
            start_new_session=True,
        )
        Result.status = process.returncode
        sysEndTime = time.time()
        stop.put(1)
        self._reset_trace_state()
        log_sources = ParamTraceCollector.collect_updated_text_sources(
            logDir,
            logFileState,
            source="system-log",
        )
        shell_sources = ParamTraceCollector.collect_updated_text_sources(
            systestShellDir,
            shellFileState,
            source="system-shell",
        )
        self.lastTraceEvents.extend(
            ParamTraceCollector.parse_events_from_text(
                process.stdout,
                source="system-stdout",
                extra={"project": self.project},
            )
        )
        self.lastTraceEvents.extend(
            ParamTraceCollector.parse_events_from_text(
                process.stderr,
                source="system-stderr",
                extra={"project": self.project},
            )
        )
        self.lastTraceEvents.extend(ParamTraceCollector.extract_events_from_text_sources(log_sources))
        self.lastTraceEvents.extend(ParamTraceCollector.extract_events_from_text_sources(shell_sources))
        self.lastExercisedConfNames = ParamTraceCollector.extract_exercised_names(self.lastTraceEvents)
        self.lastUseBackedConfNames = ParamTraceCollector.extract_use_backed_names(self.lastTraceEvents)
        self.lastTraceStatus, self.lastTraceDetails = self._summarize_trace_run(
            process.stdout or "",
            process.stderr or "",
            log_sources,
            shell_sources,
            self.lastTraceEvents,
        )
        self.lastTraceCapture = {
            "stdout_text": process.stdout or "",
            "stderr_text": process.stderr or "",
            "log_sources": log_sources,
            "shell_sources": shell_sources,
        }

        onceSysTime = sysEndTime - sysStartTime
        if recordStats:
            self.totalTime += onceSysTime
            self.totalCount += 1

            ShowStats.averageSystemTestTime = self.totalTime / self.totalCount
            ShowStats.systemTestExecSpeed = self.totalCount / self.totalTime
            ShowStats.totalSystemTestcases = self.totalCount
            ShowStats.longgestSystemTestTime = max(ShowStats.longgestSystemTestTime, onceSysTime)

        self.logger.info(
            f">>>>[systest] The return code of {testcase.filePath} system test verification is {Result.status}.")
        self.logger.info(
            f">>>>[systest] exercised params observed in this run: {len(self.lastExercisedConfNames)}"
        )
        self.logger.info(
            f">>>>[systest] use-backed exercised params observed in this run: {len(self.lastUseBackedConfNames)}"
        )
        self.logger.info(
            f">>>>[systest] trace diagnosis for this run: {self.lastTraceStatus} "
            f"(inputs={self.lastTraceDetails.get('trace_input_sources', [])}, "
            f"events={self.lastTraceDetails.get('system_event_count', 0)}, "
            f"exercised={self.lastTraceDetails.get('system_exercised_unique_param_count', 0)})"
        )
        if Result.status != 0:
            ShowStats.lastNewFailSystemTest = 0.0
            self.preFindTime = sysEndTime
            # ShowStats.totalSystemTestFailed += 1
            Result.description = process.stderr
            self.logger.info(
                f">>>>[systest] conf_file {testcase.filePath} system test failure is described as {Result.description}.")
            failType1Str = "Startup phase exception"
            failType2Str = "API request Exception"
            failType3Str = "Shutdown phase exception"
            
            if failType1Str in Result.description:
                Result.sysFailType = 1
                ShowStats.totalSystemTestFailed_Type1 += 1
                # modify confMutaionInfo
                for confItem in testcase.confItemList:
                    if confItem.isMutated == True:
                        ConfAnalyzer.confMutationInfo[confItem.name][1] += 1
                        # # update excludeConf
                        # if confItem.name not in ConfAnalyzer.excludeConf:
                        #     num1, num2 = ConfAnalyzer.confMutationInfo[confItem.name][0], ConfAnalyzer.confMutationInfo[confItem.name][1]
                        #     if num2 >= 10 and (float(num2) / num1) > 0.75:
                        #         ConfAnalyzer.excludeConf.append(confItem.name) 
            elif failType2Str in Result.description:
                Result.sysFailType = 2
                ShowStats.totalSystemTestFailed_Type2 += 1
                expList = self.dealWithExp(Result.description)
                exp = "" if len(expList) == 0 else expList[0] if len(expList) == 1 else expList[1]
                if exp != "":
                    if exp not in self.exceptionMap:
                        self.exceptionMap[exp] = 1
                    else:
                        self.exceptionMap[exp] += 1
                if exp != "":
                    # deal with exceptionMapReason
                    # testcase of different
                    diffVal = {}
                    for conf in testcase.confItemList:
                        # if value is different from orginal value, add it to diffval
                        if conf.name in self.valueMap and conf.value != self.valueMap[conf.name]:
                            if conf.name not in diffVal:
                                diffVal[conf.name] = conf.value
                    if exp not in self.exceptionMapReason:
                        self.exceptionMapReason[exp] = []          
                    if len(diffVal) != 0:
                        self.exceptionMapReason[exp].append(diffVal)
            
            elif failType3Str in Result.description:
                Result.sysFailType = 3
                ShowStats.totalSystemTestFailed_Type3 += 1
            else:
                self.logger.info(
                f">>>>[systest] conf_file {testcase.filePath} system test failure is cannot be classified.")
                Result.sysFailType = 4
            ShowStats.totalSystemTestFailed = ShowStats.totalSystemTestFailed_Type1 + ShowStats.totalSystemTestFailed_Type2 + ShowStats.totalSystemTestFailed_Type3 
        else:
            ShowStats.lastNewFailSystemTest = sysEndTime - self.preFindTime
            Result.description = "System Testing Succeed."
        self.logger.info(f">>>>[systest] exceptionMap is : {self.exceptionMap}")
        self.logger.info(f">>>>[systest] exceptionmapreason is : {self.exceptionMapReason}")
        return Result
    
    def dealWithExp(self, description:str) -> str:
        exceptionFilter = "[info_excetion]"
        res = []
        try:
            index = description.find(exceptionFilter)
            left = description[index+15:]
            alters = left.split('.')
            for al in alters:
                if al.find('Exception') != -1:
                    idx = al.find('Exception')
                    tmpRes = al[:idx+9]
                    if len(al)>len(tmpRes) and al[idx+9] == '$':
                        idx1 = al[idx+9:].find('Exception')
                        if idx1 != -1:
                            tmp = al[idx+9:]
                            tmpRes += tmp[:idx1+9]
                    res.append(tmpRes)
        except Exception as e:
            self.logger.info(e)
        return res
            
    def deleteDir(self, directory):
        if os.path.exists( directory ):
            if not os.access(directory, os.W_OK):
                os.chmod(directory, stat.S_IWRITE)
            shutil.rmtree(directory) 

    def runTest(self, testcase: Testcase, stopSoon, recordStats: bool = True, replaceConfig: bool = True) -> TestResult:
        # if Configuration.fuzzerConf['project'] == 'hbase':
        #     self.deleteDir("/home/hadoop/ecfuzz/data/app_sysTest/hbase-2.2.2-work/logs")
        logLoc = self.logLocation[Configuration.fuzzerConf["project"]]
        self._reset_trace_state()
        self.deleteDir(logLoc)
        if replaceConfig:
            self.replaceConfig(testcase)
        else:
            self.logger.info(
                f">>>>[systest] bootstrap using prepared runtime configuration as-is:"
                f" {Configuration.putConf['replace_conf_path']}"
            )
        Result = self.runSystemTestUtils(testcase, logLoc, stopSoon, recordStats=recordStats)
        return Result
    
