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

python3 - <<'PY'
from pathlib import Path

path = Path("/home/hadoop/ecfuzz/data/systest_java/hbase/hbaseapi/src/main/java/com/hbase/api/TestApi.java")
text = path.read_text()
if "org.apache.hadoop.fs.Path;" not in text:
    text = text.replace(
        "import org.apache.hadoop.hbase.TableName;\n",
        "import org.apache.hadoop.hbase.TableName;\nimport org.apache.hadoop.fs.Path;\n",
    )

marker = "    private static TableDescriptor tableDescriptor;\n"
helper = """    private static TableDescriptor tableDescriptor;\n    private static final String RUNTIME_CONF_PATH = \"/home/hadoop/ecfuzz/data/app_sysTest/hbase-2.2.2-work/conf/hbase-site.xml\";\n\n    private static Configuration loadRuntimeConfiguration() {\n        Configuration conf = HBaseConfiguration.create();\n        conf.addResource(new Path(RUNTIME_CONF_PATH));\n        String quorum = conf.get(\"hbase.zookeeper.quorum\");\n        if (quorum == null || quorum.trim().isEmpty()) {\n            conf.set(\"hbase.zookeeper.quorum\", \"127.0.0.1\");\n        }\n        String clientPort = conf.get(\"hbase.zookeeper.property.clientPort\");\n        if (clientPort == null || clientPort.trim().isEmpty()) {\n            conf.set(\"hbase.zookeeper.property.clientPort\", \"2181\");\n        }\n        return conf;\n    }\n"""
if marker in text and "loadRuntimeConfiguration()" not in text:
    text = text.replace(marker, helper)

old_init = """    public static void init() throws Exception {\n        configuration = HBaseConfiguration.create();\n        configuration.set(\"hbase.zookeeper.quorum\", \"127.0.0.1\");//\n        configuration.set(\"hbase.zookeeper.property.clientPort\", \"2181\");\n        try {\n            connection = ConnectionFactory.createConnection(configuration);\n            admin = connection.getAdmin();\n        } catch (Exception e) {\n            e.printStackTrace();\n            throw e;\n        }\n    }\n"""
new_init = """    public static void init() throws Exception {\n        configuration = loadRuntimeConfiguration();\n        try {\n            connection = ConnectionFactory.createConnection(configuration);\n            admin = connection.getAdmin();\n        } catch (Exception e) {\n            e.printStackTrace();\n            throw e;\n        }\n    }\n"""
if old_init in text:
    text = text.replace(old_init, new_init)

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

cd /home/hadoop/ecfuzz/data/systest_java/hbase/hbaseapi
mvn -q -DskipTests package
cd /home/hadoop/ecfuzz/data/systest_java/hbase/test_hbase
/usr/lib/jvm/jdk-11.0.13/bin/javac test_hbase_shell_api.java

cd /home/hadoop/ecfuzz/data/systest_java/zookeeper/zkapi
mvn -q -DskipTests package
cd /home/hadoop/ecfuzz/data/systest_java/zookeeper/test_zookeeper
/usr/lib/jvm/jdk-11.0.13/bin/javac test_zk_shell_api.java

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
