import os
import shutil
import stat
import sys, getopt
from time import time
import logging
from typing import Dict
import gc

from seedGenerator.SeedGenerator import SeedGenerator
from testValidator.TestValidator import TestValidator
from testcaseGenerator.TestcaseGenerator import TestcaseGenerator
from utils.ConfAnalyzer import ConfAnalyzer
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.ProvenanceTrackingState import ProvenanceTrackingState

from utils.InstanceCreator import InstanceCreator
from utils.Logger import Logger
from utils.ShowStats import ShowStats

import time, signal, threading

from queue import Queue

stopSoon = Queue()


class Fuzzer(object):
    def __init__(self):
        self.logger: logging.Logger = Logger.get_logger()
        self.logger.info("Initializing Fuzzer...")

        self.logger.info("Parse configurations...")
        self.commandConf: Dict[str, str] = self.getOpt()
        Configuration.parseConfiguration(self.commandConf)
        self.fuzzerConf: Dict[str, str] = Configuration.fuzzerConf
        self.putConf: Dict[str, str] = Configuration.putConf
        ExerciseGuidanceState.configure_from_current()
        ProvenanceTrackingState.configure_from_current()
        

        ShowStats.mutationStrategy = self.fuzzerConf['mutator'].split(".")[-1]
        # ShowStats.mutationStrategy = "SingleMutator"
        ShowStats.fuzzerStartTime = time.time()

        self.logger.info("Analyze PUT configurations...")
        ConfAnalyzer.analyzeConfItems()
        self.logger.info("Basic ConfItems :" + str(ConfAnalyzer.confItemsBasic))

        self.logger.info("Creating a SeedGenerator...")
        self.seedGenerator: SeedGenerator = SeedGenerator()

        self.logger.info("Creating a TestcaseGenerator...")
        mutatorClassPath = self.fuzzerConf['mutator']
        self.testcaseGenerator: TestcaseGenerator = TestcaseGenerator(InstanceCreator.getInstance(mutatorClassPath))

        self.logger.info("Creating a TestValidator...")
        self.testValidator: TestValidator = TestValidator()
        if os.path.exists(self.fuzzerConf['plot_data_path']):
            os.remove(self.fuzzerConf['plot_data_path'])

        if self.fuzzerConf['data_viewer'] == 'True':
            from utils.DataViewer import DataViewer
            self.dataViewer = DataViewer(self.fuzzerConf['data_viewer_env'])

    def sigintHandler(self, signum, frame):
        stopSoon.put(True)
        print(
            f"[fuzzer-stdout] receive SIGINT loop={ShowStats.loopCounts} "
            f"iteration={ShowStats.iterationCounts} currentJob={ShowStats.currentJob} "
            f"queueLength={ShowStats.queueLength}"
        )
        self.logger.info(f">>>>[fuzzer] excludeConf : {ConfAnalyzer.excludeConf}; confMutationInfo : {ConfAnalyzer.confMutationInfo}")
        self.logger.info(f">>>>[fuzzer] receive SIGINT")
        time.sleep(1)
        exit(0)
        # process.kill()
    
    def deleteDir(self, directory):
        if os.path.exists( directory ):
            if not os.access(directory, os.W_OK):
                os.chmod(directory, stat.S_IWRITE)
            shutil.rmtree(directory) 
            
    def getOpt(self) -> dict:
        ''' project, seed_pool_selection_ratio, seed_gen_seq_ratio, data_viewer, data_viewer_env, 
        ctests_trim_sampling,ctests_trim_scale,skip_unit_test,force_system_testing_ratio,
        require_unit_pass_for_system_test
        host_ip,host_port,run_time(/h)
        '''
        argv = sys.argv[1:]
        res = {}
        try:
            opts, args = getopt.getopt(argv, "p",["project=","seed_pool_selection_ratio=","seed_gen_seq_ratio=","data_viewer=","data_viewer_env=","ctests_trim_sampling=","ctests_trim_scale=","skip_unit_test=","force_system_testing_ratio=","require_unit_pass_for_system_test=","host_ip=","host_port=","run_time=","mutator=","systemtester=","ctest_total_time=","misconf_mode=","fuzzing_loop=","exercise_guided_mutation=","exercise_guided_explore_ratio=","use_provenance_agent=","provenance_agent_mode="])
            # opts, args = getopt.getopt(argv, ["project=","seed_pool_selection_ratio=","seed_gen_seq_ratio=","data_viewer=","data_viewer_env=","ctests_trim_sampling=","ctests_trim_scale=","skip_unit_test=","force_system_testing_ratio="])
        except:
            self.logger.info("Parameter Setting Error")
        for opt, arg in opts:
            if opt in ['--project']:
                res["project"] = arg
            elif opt in ['--seed_pool_selection_ratio']:
                res["seed_pool_selection_ratio"] = arg
            elif opt in ['--seed_gen_seq_ratio']:
                res["seed_gen_seq_ratio"] = arg
            elif opt in ['--data_viewer']:
                res["data_viewer"] = arg
            elif opt in ['--data_viewer_env']:
                res["data_viewer_env"] = arg
            elif opt in ['--ctests_trim_sampling']:
                res["ctests_trim_sampling"] = arg
            elif opt in ['--ctests_trim_scale']:
                res["ctests_trim_scale"] = arg
            elif opt in ['--skip_unit_test']:
                res["skip_unit_test"] = arg
            elif opt in ['--force_system_testing_ratio']:
                res["force_system_testing_ratio"] = arg
            elif opt in ['--require_unit_pass_for_system_test']:
                res["require_unit_pass_for_system_test"] = arg
            elif opt in ['--host_ip']:
                res["host_ip"] = arg
            elif opt in ['--host_port']:
                res["host_port"] = arg
            elif opt in ['--run_time']:
                res["run_time"] = arg
            elif opt in ['--mutator']:
                res["mutator"] = arg
            elif opt in ['--systemtester']:
                res["systemtester"] = arg
            elif opt in ['--ctest_total_time']:
                res["ctest_total_time"] = arg
            elif opt in ['--misconf_mode']:
                res["misconf_mode"] = arg
            elif opt in ['--fuzzing_loop']:
                res["fuzzing_loop"] = arg
            elif opt in ['--exercise_guided_mutation']:
                res["exercise_guided_mutation"] = arg
            elif opt in ['--exercise_guided_explore_ratio']:
                res["exercise_guided_explore_ratio"] = arg
            elif opt in ['--use_provenance_agent']:
                res["use_provenance_agent"] = arg
            elif opt in ['--provenance_agent_mode']:
                res["provenance_agent_mode"] = arg
        return res
        # for opt, arg in opts:
        #     if opt in ['--project']:
        #         self.fuzzerConf['project'] = arg
        #     elif opt in ['--seed_pool_selection_ratio']:
        #         self.fuzzerConf['seed_pool_selection_ratio'] = arg
        #     elif opt in ['--seed_gen_seq_ratio']:
        #         self.fuzzerConf['seed_gen_seq_ratio'] = arg
        #     elif opt in ['--data_viewer']:
        #         self.fuzzerConf['data_viewer'] = arg
        #     elif opt in ['--data_viewer_env']:
        #         self.fuzzerConf['data_viewer_env'] = arg
        #     elif opt in ['--ctests_trim_sampling']:
        #         self.fuzzerConf['ctests_trim_sampling'] = arg
        #     elif opt in ['--ctests_trim_scale']:
        #         self.fuzzerConf['ctests_trim_scale'] = arg
        #     elif opt in ['--skip_unit_test']:
        #         self.fuzzerConf['skip_unit_test'] = arg
        #     elif opt in ['--force_system_testing_ratio']:
        #         self.fuzzerConf['force_system_testing_ratio'] = arg
            
    def run(self):
        """
        The run function is the main function of the fuzzer. It is responsible for
        looping through all the test cases and running them against a target. The
        fuzzer will run each test case in order, one after another, until it has reached
        the end of its list, or it has reached a maximum number of loops (if specified).
        """
        # firstly, delete execs
        self.testValidator.getCov.delete_execs()
        if self.fuzzerConf['data_viewer'] == 'True':
            from utils.DataViewer import startDrawing
            startDrawing(self.dataViewer)

        ShowStats.initPlotData()
        ShowStats.writeToPlotData()

        signal.signal(signal.SIGINT, self.sigintHandler)
        t1 = threading.Thread(target=ShowStats.run, args=[stopSoon])
        t1.start()
        fuzzingLoop = int(self.fuzzerConf['fuzzing_loop'])

        self.deleteDir(Configuration.fuzzerConf['unit_testcase_dir'])
        self.deleteDir(Configuration.fuzzerConf['unit_test_results_dir'])
        self.deleteDir(Configuration.fuzzerConf['sys_test_results_dir'])
        self.deleteDir(Configuration.fuzzerConf['sys_testcase_fail_dir'])

        # print("\033[37m")
        try:
            stop_reason = "unknown"
            self.testValidator.runExerciseBootstrap(stopSoon)
            if fuzzingLoop > 0:
                self.logger.info(f"Fuzzer ready to run for {fuzzingLoop} loops...")
                for _ in range(fuzzingLoop):
                    try:
                        if (not stopSoon.empty()):
                            stop_reason = "stopSoon queue non-empty"
                            t1.join()
                            break
                    except Exception as e:
                        stop_reason = f"stopSoon check exception: {e!r}"
                        print(e)
                        break
                    try:
                        self.loop(stopSoon)
                    except BaseException as e:
                        stop_reason = f"loop exception: {e!r}"
                        print(
                            f"[fuzzer-stdout] loop execution failed at loop={ShowStats.loopCounts} "
                            f"iteration={ShowStats.iterationCounts} currentJob={ShowStats.currentJob} "
                            f"queueLength={ShowStats.queueLength} exc={e!r}"
                        )
                        self.logger.exception(
                            "loop execution failed at loop=%s iteration=%s currentJob=%s queueLength=%s",
                            ShowStats.loopCounts,
                            ShowStats.iterationCounts,
                            ShowStats.currentJob,
                            ShowStats.queueLength,
                        )
                        break
            else:
                self.logger.info("Fuzzer ready to run forever...")
                while True:
                    try:
                        if not stopSoon.empty():
                            stop_reason = "stopSoon queue non-empty"
                            t1.join()
                            break
                    except Exception as e:
                        stop_reason = f"stopSoon check exception: {e!r}"
                        print(e)
                        break
                    try:
                        self.loop(stopSoon)
                    except BaseException as e:
                        stop_reason = f"loop exception: {e!r}"
                        print(
                            f"[fuzzer-stdout] loop execution failed at loop={ShowStats.loopCounts} "
                            f"iteration={ShowStats.iterationCounts} currentJob={ShowStats.currentJob} "
                            f"queueLength={ShowStats.queueLength} exc={e!r}"
                        )
                        self.logger.exception(
                            "loop execution failed at loop=%s iteration=%s currentJob=%s queueLength=%s",
                            ShowStats.loopCounts,
                            ShowStats.iterationCounts,
                            ShowStats.currentJob,
                            ShowStats.queueLength,
                        )
                        break
        finally:
            stopSoon.put(True)
            print(
                f"[fuzzer-stdout] shutting down stop_reason={stop_reason} "
                f"elapsed_seconds={time.time() - ShowStats.fuzzerStartTime} "
                f"configured_run_time_hours={Configuration.fuzzerConf['run_time']} "
                f"loop={ShowStats.loopCounts} iteration={ShowStats.iterationCounts} "
                f"queueLength={ShowStats.queueLength} acceptedSeedCount={ShowStats.acceptedSeedCount}"
            )
            self.logger.info(
                "fuzzer shutting down: stop_reason=%s elapsed_seconds=%s configured_run_time_hours=%s loop=%s iteration=%s queueLength=%s acceptedSeedCount=%s",
                stop_reason,
                time.time() - ShowStats.fuzzerStartTime,
                Configuration.fuzzerConf['run_time'],
                ShowStats.loopCounts,
                ShowStats.iterationCounts,
                ShowStats.queueLength,
                ShowStats.acceptedSeedCount,
            )
            # write data to db
            result_data = {}
            result_data['totalSystemTestFailed'] = ShowStats.totalSystemTestFailed
            result_data['totalSystemTestFailed_Type1'] = ShowStats.totalSystemTestFailed_Type1
            result_data['totalSystemTestFailed_Type2'] = ShowStats.totalSystemTestFailed_Type2
            result_data['totalSystemTestFailed_Type3'] = ShowStats.totalSystemTestFailed_Type3
            result_data['system_testcase_num'] = ShowStats.totalSystemTestcases
            if self.testValidator.useMongo == 'True':
                self.testValidator.mongoDb.insert_result_to_db(result_data)
                # save exception map
                self.testValidator.mongoDb.insert_exception_to_db(self.testValidator.sysTester.exceptionMap)
                self.logger.info(f'map reason is: {self.testValidator.sysTester.exceptionMapReason}')
                self.testValidator.mongoDb.insert_map_to_db("ExceptionMapReason", self.testValidator.sysTester.exceptionMapReason)
            self.testValidator.comparisonMetrics.finalize()
            self.logger.info(f">>>>[fuzzer] hava a good time")
            print("\033[37m")
            if self.fuzzerConf['data_viewer'] == 'True':
                from utils.DataViewer import stopDrawing
                stopDrawing(self.dataViewer)

    def loop(self, stopSoon: Queue):
        """
        The loop function is the core of the fuzzer. It is meant to be run in a while loop,
        and it accomplishes the following:
            1. Generate a seed from our seed pool (see SeedPool class)
            2. Mutate this seed into multiple test cases using our TestcaseGenerator class (see TestcaseGenerator class)
            3. Run each of these test cases through our TestValidator and collect their results (see TestValidator class)

            If any result yields an interesting value, we add that seed back to our pool for future iterations.
        """
        # run time limit
        elapsed_seconds = time.time() - ShowStats.fuzzerStartTime
        configured_run_time_hours = int(Configuration.fuzzerConf['run_time'])
        if elapsed_seconds > 3600 * configured_run_time_hours:
            self.logger.info(
                "runtime limit reached: elapsed_seconds=%s configured_run_time_hours=%s loop=%s iteration=%s",
                elapsed_seconds,
                configured_run_time_hours,
                ShowStats.loopCounts,
                ShowStats.iterationCounts,
            )
            # need to exit
            stopSoon.put(True)
        self.logger.info("Generator a Seed from SeedGenerator")
        self.seedGenerator.updateConfMutable()
        seed = self.seedGenerator.generateSeed()
        ShowStats.queueLength = len(self.seedGenerator.seedPool)
        testcasePerSeed = int(self.fuzzerConf['testcase_per_seed'])
        for _ in range(testcasePerSeed):
            self.logger.info(">>>>[fuzzer] start to mutate seed")
            self.logger.info(">>>>[fuzzer] seed len is : {}".format(seed.confItemList.__len__()))
            testcase = self.testcaseGenerator.mutate(seed)
            self.logger.info(">>>>[fuzzer] mutated testcase's length is : {}".format(len(testcase.confItemList)))
            utResult, sysResult, trimmedTestcase = self.testValidator.runTest(testcase, stopSoon)
            self.logger.info(">>>>[fuzzer] testValidator done")
            if (utResult != None) and (utResult.status == 1) and (sysResult != None) and (sysResult.status == 0):
                self.seedGenerator.addSeedToPool(trimmedTestcase)
                ShowStats.acceptedSeedCount += 1
            self.logger.info(">>>>[fuzzer] handle seed done")
            ShowStats.writeToPlotData()
            ShowStats.iterationCounts += 1
            self.testValidator.comparisonMetrics.record_snapshot()
        ShowStats.loopCounts += 1
        # if ShowStats.loopCounts % 5 == 0:
        #     # gc on each five round
        #     gc.collect()
        self.logger.info("run() loop end -150")


if __name__ == "__main__":
    fuzzer = Fuzzer() 
    fuzzer.run()
