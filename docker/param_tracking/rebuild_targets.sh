#!/usr/bin/env bash
set -euxo pipefail

HADOOP_ROOT=/home/hadoop/ecfuzz/data/app/ctest-hadoop
HADOOP_COMMON_TARGET=${HADOOP_ROOT}/hadoop-common-project/hadoop-common/target
HADOOP_RUNTIME=/home/hadoop/ecfuzz/data/app_sysTest/hadoop-2.8.5-work
HBASE_ROOT=/home/hadoop/ecfuzz/data/app/ctest-hbase
HBASE_COMMON_TARGET=${HBASE_ROOT}/hbase-common/target
HBASE_RUNTIME=/home/hadoop/ecfuzz/data/app_sysTest/hbase-2.2.2-work

ZOOKEEPER_ROOT=/home/hadoop/ecfuzz/data/app/ctest-zookeeper
ZOOKEEPER_TARGET=${ZOOKEEPER_ROOT}/zookeeper-server/target
ZOOKEEPER_RUNTIME=/home/hadoop/ecfuzz/data/app_sysTest/zookeeper-3.5.6-work

ALLUXIO_ROOT=/home/hadoop/ecfuzz/data/app/ctest-alluxio
ALLUXIO_RUNTIME=/home/hadoop/ecfuzz/data/app_sysTest/alluxio-2.1.0-work
ALLUXIO_CLIENT_ASSEMBLY=${ALLUXIO_ROOT}/assembly/client/target/alluxio-assembly-client-2.1.0-jar-with-dependencies.jar
ALLUXIO_SERVER_ASSEMBLY=${ALLUXIO_ROOT}/assembly/server/target/alluxio-assembly-server-2.1.0-jar-with-dependencies.jar

cd "${HADOOP_ROOT}"
mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests
cp -f "${HADOOP_COMMON_TARGET}/hadoop-common-2.8.5.jar" \
  "${HADOOP_RUNTIME}/share/hadoop/common/hadoop-common-2.8.5.jar"
cp -f "${HADOOP_COMMON_TARGET}/hadoop-common-2.8.5-tests.jar" \
  "${HADOOP_RUNTIME}/share/hadoop/common/hadoop-common-2.8.5-tests.jar"
cp -f "${HADOOP_COMMON_TARGET}/hadoop-common-2.8.5.jar" \
  "${HADOOP_RUNTIME}/share/hadoop/httpfs/tomcat/webapps/webhdfs/WEB-INF/lib/hadoop-common-2.8.5.jar"
cp -f "${HADOOP_COMMON_TARGET}/hadoop-common-2.8.5.jar" \
  "${HADOOP_RUNTIME}/share/hadoop/kms/tomcat/webapps/kms/WEB-INF/lib/hadoop-common-2.8.5.jar"
cp -f "${HADOOP_COMMON_TARGET}/hadoop-common-2.8.5.jar" \
  "${HBASE_RUNTIME}/lib/hadoop-common-2.8.5.jar"

python3 - <<'PY'
from pathlib import Path

path = Path("/home/hadoop/ecfuzz/data/app/ctest-hbase/hbase-common/src/main/java/org/apache/hadoop/hbase/HBaseConfiguration.java")
text = path.read_text()
old = "      destConf.set(e.getKey(), e.getValue());"
new = "      destConf.set(e.getKey(), e.getValue(), null, false); //CTEST"
if old in text:
    text = text.replace(old, new)
path.write_text(text)
PY

cd "${HBASE_ROOT}"
mvn -pl hbase-common -am install -DskipTests
cp -f "${HBASE_COMMON_TARGET}/hbase-common-2.2.2.jar" \
  "${HBASE_RUNTIME}/lib/hbase-common-2.2.2.jar"
cp -f "${HBASE_COMMON_TARGET}/hbase-common-2.2.2-tests.jar" \
  "${HBASE_RUNTIME}/lib/hbase-common-2.2.2-tests.jar"

cd "${ZOOKEEPER_ROOT}"
mvn -pl zookeeper-server -am install -DskipTests
cp -f "${ZOOKEEPER_TARGET}/zookeeper-3.5.6.jar" \
  "${ZOOKEEPER_RUNTIME}/lib/zookeeper-3.5.6.jar"

python3 - <<'PY'
from pathlib import Path
import re

path = Path("/home/hadoop/ecfuzz/data/app/ctest-alluxio/pom.xml")
text = path.read_text()
text = re.sub(
    r"(<repository>\s*<id>alluxio\.artifacts</id>\s*<url>).*?(</url>\s*</repository>)",
    lambda match: (
        f"{match.group(1)}file:///home/hadoop/.m2/repository{match.group(2)}"
    ),
    text,
    flags=re.S,
)
for repo_id in ("mapr-repo", "spring-releases", "HDPReleases"):
    text = re.sub(
        rf"\s*<repository>(?:(?!</repository>).)*?<id>{re.escape(repo_id)}</id>(?:(?!</repository>).)*?</repository>\s*",
        "\n",
        text,
        flags=re.S,
    )
path.write_text(text)
PY

cd "${ALLUXIO_ROOT}"
mvn -nsu -pl assembly/client,assembly/server -am install -DskipTests \
  -Dcheckstyle.skip -Dlicense.skip -Dfindbugs.skip -Dmaven.javadoc.skip=true
cp -f "${ALLUXIO_CLIENT_ASSEMBLY}" \
  "${ALLUXIO_RUNTIME}/assembly/alluxio-client-2.1.0.jar"
cp -f "${ALLUXIO_SERVER_ASSEMBLY}" \
  "${ALLUXIO_RUNTIME}/assembly/alluxio-server-2.1.0.jar"
cp -f "${ALLUXIO_CLIENT_ASSEMBLY}" \
  "${ALLUXIO_RUNTIME}/client/alluxio-2.1.0-client.jar"
