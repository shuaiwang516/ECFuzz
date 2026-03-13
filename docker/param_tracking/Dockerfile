FROM ecfuzz/ecfuzz:1.2

USER root

COPY --chown=hadoop:hadoop src/fuzzer.py /home/hadoop/ecfuzz/src/fuzzer.py
COPY --chown=hadoop:hadoop src/dataModel/Seed.py /home/hadoop/ecfuzz/src/dataModel/Seed.py
COPY --chown=hadoop:hadoop src/dataModel/Testcase.py /home/hadoop/ecfuzz/src/dataModel/Testcase.py
COPY --chown=hadoop:hadoop src/seedGenerator/SeedGenerator.py /home/hadoop/ecfuzz/src/seedGenerator/SeedGenerator.py
COPY --chown=hadoop:hadoop src/testcaseGenerator/Mutator.py /home/hadoop/ecfuzz/src/testcaseGenerator/Mutator.py
COPY --chown=hadoop:hadoop src/testcaseGenerator/SingleMutator.py /home/hadoop/ecfuzz/src/testcaseGenerator/SingleMutator.py
COPY --chown=hadoop:hadoop src/testcaseGenerator/SmartMutator.py /home/hadoop/ecfuzz/src/testcaseGenerator/SmartMutator.py
COPY --chown=hadoop:hadoop src/testcaseGenerator/StackedMutator.py /home/hadoop/ecfuzz/src/testcaseGenerator/StackedMutator.py
COPY --chown=hadoop:hadoop src/testValidator/UnitTester.py /home/hadoop/ecfuzz/src/testValidator/UnitTester.py
COPY --chown=hadoop:hadoop src/testValidator/SystemTester.py /home/hadoop/ecfuzz/src/testValidator/SystemTester.py
COPY --chown=hadoop:hadoop src/testValidator/TestValidator.py /home/hadoop/ecfuzz/src/testValidator/TestValidator.py
COPY --chown=hadoop:hadoop src/testValidator/run_unit_test_utils.py /home/hadoop/ecfuzz/src/testValidator/run_unit_test_utils.py
COPY --chown=hadoop:hadoop src/utils/ComparisonMetricsRecorder.py /home/hadoop/ecfuzz/src/utils/ComparisonMetricsRecorder.py
COPY --chown=hadoop:hadoop src/utils/Configuration.py /home/hadoop/ecfuzz/src/utils/Configuration.py
COPY --chown=hadoop:hadoop src/utils/ExerciseGuidanceState.py /home/hadoop/ecfuzz/src/utils/ExerciseGuidanceState.py
COPY --chown=hadoop:hadoop src/utils/ParamTraceCollector.py /home/hadoop/ecfuzz/src/utils/ParamTraceCollector.py
COPY --chown=hadoop:hadoop src/utils/ProvenanceTrackingState.py /home/hadoop/ecfuzz/src/utils/ProvenanceTrackingState.py
COPY --chown=hadoop:hadoop src/utils/ShowStats.py /home/hadoop/ecfuzz/src/utils/ShowStats.py
COPY --chown=hadoop:hadoop data/fuzzer/fuzzing.conf /home/hadoop/ecfuzz/data/fuzzer/fuzzing.conf
COPY --chown=hadoop:hadoop java/experimental-provenance-agent /home/hadoop/ecfuzz/java/experimental-provenance-agent

COPY --chown=hadoop:hadoop docker/param_tracking/overrides/hadoop/Configuration.java /home/hadoop/ecfuzz/data/app/ctest-hadoop/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/conf/Configuration.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/zookeeper/ServerConfig.java /home/hadoop/ecfuzz/data/app/ctest-zookeeper/zookeeper-server/src/main/java/org/apache/zookeeper/server/ServerConfig.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/zookeeper/QuorumPeerConfig.java /home/hadoop/ecfuzz/data/app/ctest-zookeeper/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerConfig.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/zookeeper/QuorumPeerMain.java /home/hadoop/ecfuzz/data/app/ctest-zookeeper/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerMain.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/zookeeper/App.java /home/hadoop/ecfuzz/data/systest_java/zookeeper/zkapi/src/main/java/com/zookeeper/api/App.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/zookeeper/test_zk_shell_api.java /home/hadoop/ecfuzz/data/systest_java/zookeeper/test_zookeeper/test_zk_shell_api.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/alluxio/AlluxioProperties.java /home/hadoop/ecfuzz/data/app/ctest-alluxio/core/common/src/main/java/alluxio/conf/AlluxioProperties.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/alluxio/InstancedConfiguration.java /home/hadoop/ecfuzz/data/app/ctest-alluxio/core/common/src/main/java/alluxio/conf/InstancedConfiguration.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/alluxio/SpecificPathConfiguration.java /home/hadoop/ecfuzz/data/app/ctest-alluxio/core/common/src/main/java/alluxio/conf/path/SpecificPathConfiguration.java
COPY --chown=hadoop:hadoop docker/param_tracking/overrides/hbase/test_hbase_shell_api.java /home/hadoop/ecfuzz/data/systest_java/hbase/test_hbase/test_hbase_shell_api.java
COPY --chown=hadoop:hadoop docker/param_tracking/rebuild_targets.sh /tmp/rebuild_targets.sh

RUN chmod +x /tmp/rebuild_targets.sh

USER hadoop

RUN mkdir -p /home/hadoop/ecfuzz/agent/provenance-agent && \
    cd /home/hadoop/ecfuzz/java/experimental-provenance-agent && \
    mvn -q -DskipTests package && \
    cp -f target/ecfuzz-provenance-agent.jar \
      /home/hadoop/ecfuzz/agent/provenance-agent/ecfuzz-provenance-agent.jar

RUN /tmp/rebuild_targets.sh

USER root
RUN rm -f /tmp/rebuild_targets.sh
USER hadoop
