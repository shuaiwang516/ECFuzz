import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;

public class test_zk_shell_api {
    private static final String DEFAULT_CONF_PATH =
            "/home/hadoop/ecfuzz/data/app_sysTest/zookeeper-3.5.6-work/conf/zoo.cfg";
    private static int api_pid = 0;
    private static boolean isFinished;

    public static void main(String[] args) throws Throwable {
        String cur_path = System.getProperty("user.dir");
        System.out.println(cur_path);
        String zk_path = new File(cur_path).getParent();
        String app_path = new File(zk_path).getParent();
        String data_path = new File(app_path).getParent();

        String cmd1 = data_path + "/app_sysTest/zookeeper-3.5.6-work/bin/zkServer.sh start";
        String cmd_api = "cd " + zk_path + "/zkapi && ./test_zkapi.sh";

        Map<String, String> config = loadRuntimeConfig();
        String host = clientHost(config);
        int port = clientPort(config);
        resetRuntimeStorage(config);

        System.out.println("zk start command: " + cmd1);
        System.out.println("zk api command: " + cmd_api);
        System.out.println("waiting for ZooKeeper on " + host + ":" + port);

        ProcessBuilder pb1 = new ProcessBuilder("/bin/bash", "-c", cmd1);
        pb1.redirectOutput(new File("start_zk"));
        pb1.redirectErrorStream(true);
        pb1.start();

        if (!waitForPortOpen(host, port, 30000)) {
            throw new RuntimeException("Startup phase exception: ZooKeeper did not become reachable on " + host + ":" + port);
        }

        int tmp = 0;
        String line = "";
        try {
            ProcessBuilder pb3 = new ProcessBuilder("/bin/bash", "-c", cmd_api);
            pb3.redirectErrorStream(true);
            TimeoutThread timeoutMonitor = new TimeoutThread();
            timeoutMonitor.start();
            Process p3 = pb3.start();
            isFinished = false;
            api_pid = processPid(p3);

            BufferedReader br = new BufferedReader(new InputStreamReader(p3.getInputStream(), StandardCharsets.UTF_8));
            String filter = "Exception";
            while ((line = br.readLine()) != null) {
                System.out.println(line);
                if (line.contains(filter)) {
                    break;
                }
            }

            tmp = p3.waitFor();
            isFinished = true;
            if (timeoutMonitor.isAlive()) {
                timeoutMonitor.interrupt();
            }
            System.out.println("zk api finished with status " + tmp);
        } catch (Exception e) {
            e.printStackTrace();
        }

        if (tmp != 0) {
            stopServer(data_path);
            if (tmp == 137) {
                throw new RuntimeException("API request Exception: The API script is hang[info_excetion]" + line);
            }
            throw new RuntimeException("API request Exception: Operation exception[info_excetion]" + line);
        }

        stopServer(data_path);
        if (!waitForPortClosed(host, port, 15000)) {
            Integer pid = findJavaPid("org.apache.zookeeper.server.quorum.QuorumPeerMain");
            if (pid != null) {
                killPid(pid.intValue());
            }
            if (!waitForPortClosed(host, port, 5000)) {
                throw new RuntimeException("Shutdown phase exception");
            }
        }
        System.out.println("zk is shut down!");
    }

    private static void stopServer(String dataPath) throws IOException, InterruptedException {
        String cmd2 = dataPath + "/app_sysTest/zookeeper-3.5.6-work/bin/zkServer.sh stop";
        ProcessBuilder pb = new ProcessBuilder("/bin/bash", "-c", cmd2);
        pb.redirectOutput(new File("stop_zk"));
        pb.redirectErrorStream(true);
        pb.start();
        Thread.sleep(3000);
    }

    private static Map<String, String> loadRuntimeConfig() throws IOException {
        Map<String, String> values = new HashMap<String, String>();
        if (!Files.exists(Paths.get(DEFAULT_CONF_PATH))) {
            return values;
        }
        for (String line : Files.readAllLines(Paths.get(DEFAULT_CONF_PATH), StandardCharsets.UTF_8)) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                continue;
            }
            int index = trimmed.indexOf('=');
            if (index <= 0) {
                continue;
            }
            values.put(trimmed.substring(0, index).trim(), trimmed.substring(index + 1).trim());
        }
        return values;
    }

    private static String clientHost(Map<String, String> config) {
        String host = config.get("clientPortAddress");
        if (host == null || host.trim().isEmpty() || "0.0.0.0".equals(host.trim())) {
            return "127.0.0.1";
        }
        return host.trim();
    }

    private static int clientPort(Map<String, String> config) {
        String port = config.get("clientPort");
        if (port == null || port.trim().isEmpty()) {
            return 2181;
        }
        try {
            return Integer.parseInt(port.trim());
        } catch (NumberFormatException e) {
            return 2181;
        }
    }

    private static void resetRuntimeStorage(Map<String, String> config) throws IOException {
        resetPath(config.get("dataDir"));
        String dataLogDir = config.get("dataLogDir");
        if (dataLogDir != null && !dataLogDir.trim().isEmpty()) {
            resetPath(dataLogDir);
        }
    }

    private static void resetPath(String pathValue) throws IOException {
        if (pathValue == null) {
            return;
        }
        String trimmed = pathValue.trim();
        if (trimmed.isEmpty()) {
            return;
        }
        Path path = Paths.get(trimmed);
        if (Files.exists(path)) {
            deleteRecursively(path.toFile());
        }
        Files.createDirectories(path);
    }

    private static void deleteRecursively(File file) throws IOException {
        if (file == null || !file.exists()) {
            return;
        }
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteRecursively(child);
            }
        }
        if (!file.delete()) {
            throw new IOException("Failed to delete " + file.getAbsolutePath());
        }
    }

    private static boolean waitForPortOpen(String host, int port, int timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (canConnect(host, port)) {
                return true;
            }
            Thread.sleep(1000);
        }
        return false;
    }

    private static boolean waitForPortClosed(String host, int port, int timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (!canConnect(host, port)) {
                return true;
            }
            Thread.sleep(1000);
        }
        return !canConnect(host, port);
    }

    private static boolean canConnect(String host, int port) {
        if (port <= 0 || port > 65535) {
            return false;
        }
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 1000);
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    private static Integer findJavaPid(String mainClass) {
        try {
            ProcessBuilder pb = new ProcessBuilder("/usr/lib/jvm/jdk-11.0.13/bin/jps", "-l");
            Process process = pb.start();
            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
            String line;
            while ((line = reader.readLine()) != null) {
                String trimmed = line.trim();
                if (trimmed.endsWith(mainClass)) {
                    String[] parts = trimmed.split("\\s+", 2);
                    return Integer.valueOf(parts[0]);
                }
            }
        } catch (Exception e) {
            return null;
        }
        return null;
    }

    private static void killPid(int pid) {
        try {
            Runtime.getRuntime().exec(new String[] { "kill", "-15", String.valueOf(pid) });
            Thread.sleep(3000);
            Runtime.getRuntime().exec(new String[] { "kill", "-9", String.valueOf(pid) });
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static int processPid(Process process) {
        try {
            Object value = Process.class.getMethod("pid").invoke(process);
            if (value instanceof Long) {
                return (int) ((Long) value).longValue();
            }
        } catch (Exception e) {
            return -1;
        }
        return -1;
    }

    public static class TimeoutThread extends Thread {
        int timeout = 60000;

        @Override
        public void run() {
            try {
                sleep(timeout);
            } catch (InterruptedException e) {
                if (isFinished) {
                    return;
                }
            }
            try {
                Runtime.getRuntime().exec(new String[] { "kill", "-15", String.valueOf(api_pid) });
                Thread.sleep(3000);
                Runtime.getRuntime().exec(new String[] { "kill", "-9", String.valueOf(api_pid) });
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}
