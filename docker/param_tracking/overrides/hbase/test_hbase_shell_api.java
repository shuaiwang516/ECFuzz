import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Date;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class test_hbase_shell_api {
    private static int hbase_pid = 0;
    private static int api_pid = 0;
    private static boolean isFinished;
    private static Logger log = Logger.getLogger("test_hbase_shell_api");

    public static void main(String[] args) throws Throwable {
        log.setLevel(Level.ALL);
        FileHandler fileHandler = new FileHandler("./logs/test_hbase_shell_api.log", true);
        fileHandler.setLevel(Level.ALL);
        fileHandler.setFormatter(new LogFormatter());
        log.addHandler(fileHandler);

        String cur_path = System.getProperty("user.dir");
        String hbase_path = new File(cur_path).getParent();
        String app_path = new File(hbase_path).getParent();
        String data_path = new File(app_path).getParent();

        cleanupWalDirs();

        String startCmd = data_path + "/app_sysTest/hbase-2.2.2-work/bin/start-hbase.sh";
        ProcessBuilder pb1 = new ProcessBuilder("/bin/bash", "-c", startCmd);
        pb1.redirectOutput(new File("start_hbase"));
        pb1.redirectErrorStream(true);
        pb1.start();
        log.info("HBase is starting");

        Integer pid = waitForJavaProcess("org.apache.hadoop.hbase.master.HMaster", 30000);
        if (pid == null) {
            throw new RuntimeException("Startup phase exception: Unable to start HMaster");
        }
        hbase_pid = pid.intValue();
        log.info("HBase is running in pid " + hbase_pid);

        String cmd_api = "cd " + hbase_path + "/hbaseapi && ./test_hbaseapi.sh";
        int tmp_api = 0;
        String line = "";

        try {
            ProcessBuilder pb_api = new ProcessBuilder("/bin/bash", "-c", cmd_api);
            pb_api.redirectErrorStream(true);
            TimeoutThread timeoutMonitor = new TimeoutThread(60000);
            timeoutMonitor.start();
            Process p = pb_api.start();
            isFinished = false;
            api_pid = processPid(p);

            log.info("HBase is accepting API requests in pid " + api_pid);

            BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8));
            String filter = "Exception";
            while ((line = br.readLine()) != null) {
                System.out.println(line);
                if (line.contains(filter)) {
                    break;
                }
            }

            tmp_api = p.waitFor();
            log.info("HBase API finished with " + tmp_api);
            isFinished = true;
            if (timeoutMonitor.isAlive()) {
                timeoutMonitor.interrupt();
            }
        } catch (Exception e) {
            e.printStackTrace();
        }

        if (tmp_api != 0) {
            stopHBase(data_path);
            Integer masterPid = findJavaPid("org.apache.hadoop.hbase.master.HMaster");
            if (masterPid != null) {
                hbase_pid = masterPid.intValue();
                killPid(hbase_pid);
            }
            Integer apiPid = findJavaPid("com.hbase.api.TestApi");
            if (apiPid != null) {
                killPid(apiPid.intValue());
            }

            if (tmp_api == 137) {
                throw new RuntimeException("API request Exception: The API script is hang[info_excetion]" + line);
            }
            if (masterPid != null) {
                throw new RuntimeException("API request Exception: Operation exception:[info_excetion]" + line);
            }
            throw new RuntimeException("Startup phase exception: HMaster initialization failure and dropped out");
        }

        stopHBase(data_path);
        if (waitForJavaProcessGone("org.apache.hadoop.hbase.master.HMaster", 20000) == false) {
            Integer masterPid = findJavaPid("org.apache.hadoop.hbase.master.HMaster");
            if (masterPid != null) {
                killPid(masterPid.intValue());
            }
            throw new RuntimeException("Shutdown phase exception");
        }

        Integer apiPid = findJavaPid("com.hbase.api.TestApi");
        if (apiPid != null) {
            killPid(apiPid.intValue());
            throw new RuntimeException("API request Exception: The API script is not closed properly!");
        }

        log.info("HBase is shut down");
    }

    private static void cleanupWalDirs() throws IOException, InterruptedException {
        execIgnoreExit("cd /home/hadoop/hbase-2.2.2-work/hbase-tmp/MasterProcWALs; rm -f *");
        execIgnoreExit("cd /home/hadoop/hbase-2.2.2-work/hbase-tmp/oldWALs; rm -f *");
        Thread.sleep(1500);
    }

    private static void stopHBase(String dataPath) throws IOException, InterruptedException {
        String stopCmd = dataPath + "/app_sysTest/hbase-2.2.2-work/bin/hbase-daemon.sh stop master";
        ProcessBuilder pb2 = new ProcessBuilder("/bin/bash", "-c", stopCmd);
        pb2.redirectOutput(new File("stop_hbase"));
        pb2.redirectErrorStream(true);
        TimeoutThread timeoutMonitor1 = new TimeoutThread(20000);
        timeoutMonitor1.start();
        isFinished = false;
        Process p2 = pb2.start();
        api_pid = processPid(p2);
        p2.waitFor();
        isFinished = true;
        if (timeoutMonitor1.isAlive()) {
            timeoutMonitor1.interrupt();
        }
    }

    private static void execIgnoreExit(String cmd) throws IOException {
        new ProcessBuilder("/bin/bash", "-c", cmd).start();
    }

    private static Integer waitForJavaProcess(String mainClass, int timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            Integer pid = findJavaPid(mainClass);
            if (pid != null) {
                return pid;
            }
            Thread.sleep(1000);
        }
        return null;
    }

    private static boolean waitForJavaProcessGone(String mainClass, int timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (findJavaPid(mainClass) == null) {
                return true;
            }
            Thread.sleep(1000);
        }
        return findJavaPid(mainClass) == null;
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
            log.info("Unable to query java process list: " + e.getMessage());
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
        int timeout;

        public TimeoutThread(int timeout) {
            this.timeout = timeout;
        }

        @Override
        public void run() {
            try {
                sleep(timeout);
            } catch (InterruptedException e) {
                if (isFinished) {
                    return;
                }
            }
            String[] cmd_th = new String[] { "kill", "-9", String.valueOf(api_pid) };
            try {
                log.info("want to send kill signal to TestApi" + Arrays.toString(cmd_th) + " . " + api_pid);
                Runtime.getRuntime().exec(new String[] { "kill", "-15", String.valueOf(api_pid) });
                Thread.sleep(3000);
                Runtime.getRuntime().exec(new String[] { "kill", "-9", String.valueOf(api_pid) });
                log.info("send kill signal to TestApi");
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}

class LogFormatter extends Formatter {
    @Override
    public String format(LogRecord record) {
        Date date = new Date();
        String sDate = date.toString();
        return "[" + sDate + "]" + "[" + record.getLevel() + "]" + record.getClass() + record.getMessage() + "\n";
    }
}
