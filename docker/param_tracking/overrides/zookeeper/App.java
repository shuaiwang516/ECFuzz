package com.zookeeper.api;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.zookeeper.CreateMode;
import org.apache.zookeeper.KeeperException;
import org.apache.zookeeper.WatchedEvent;
import org.apache.zookeeper.Watcher;
import org.apache.zookeeper.ZooDefs.Ids;
import org.apache.zookeeper.ZooKeeper;
import org.apache.zookeeper.data.Stat;

public class App {
    private static final String DEFAULT_CONF_PATH =
            "/home/hadoop/ecfuzz/data/app_sysTest/zookeeper-3.5.6-work/conf/zoo.cfg";
    private static ZooKeeper zk = null;

    public static void createConnection(String zkHost, int timeOut) throws Exception {
        try {
            zk = new ZooKeeper(zkHost, timeOut, new Watcher() {
                public void process(WatchedEvent event) {
                    System.out.println("Connected, event type=" + event.getType());
                }
            });
        } catch (IOException e) {
            System.out.println("Connection failed, please check the ZooKeeper address");
            e.printStackTrace();
            throw e;
        }
    }

    public static void creatNode(String nodePath, String nodeData) throws Exception {
        try {
            zk.create(nodePath, nodeData.getBytes(StandardCharsets.UTF_8), Ids.OPEN_ACL_UNSAFE, CreateMode.PERSISTENT);
            System.out.println("Created node " + nodePath + " with payload " + nodeData);
        } catch (KeeperException e) {
            System.out.println("Node already exists, create failed");
            e.printStackTrace();
            throw e;
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    public static void readNode(String nodePath) throws Exception {
        try {
            System.out.println(nodePath + " content=" + new String(zk.getData(nodePath, false, null), StandardCharsets.UTF_8));
        } catch (KeeperException e) {
            System.out.println("Requested node does not exist: " + nodePath);
            e.printStackTrace();
            throw e;
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    public static void getChild(String path) throws Exception {
        try {
            List<String> list = zk.getChildren(path, false);
            if (list.isEmpty()) {
                System.out.println(path + " has no child nodes");
            } else {
                System.out.println(path + " child nodes:");
                for (String child : list) {
                    System.out.println("child=" + child);
                }
            }
        } catch (KeeperException e) {
            e.printStackTrace();
            throw e;
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    public static Stat isExists(String nodePath) throws Exception {
        try {
            return zk.exists(nodePath, true);
        } catch (KeeperException e) {
            e.printStackTrace();
            throw e;
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    public static void updateNode(String nodePath, String modifyNodeData) throws Exception {
        try {
            zk.setData(nodePath, modifyNodeData.getBytes(StandardCharsets.UTF_8), -1);
            System.out.println("Updated node " + nodePath + " to " + modifyNodeData);
        } catch (KeeperException e) {
            System.out.println("Update failed, node does not exist: " + nodePath);
            e.printStackTrace();
            throw e;
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    public static void deleteNode(String nodePath) throws Exception {
        try {
            zk.delete(nodePath, -1);
            System.out.println("Deleted node " + nodePath);
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        } catch (KeeperException e) {
            System.out.println("Delete failed, node missing or parent not empty");
            e.printStackTrace();
            throw e;
        }
    }

    public static void closeConnection() throws Exception {
        try {
            zk.close();
            System.out.println("Closed connection");
        } catch (InterruptedException e) {
            e.printStackTrace();
            throw e;
        }
    }

    private static String runtimeConfPath() {
        String path = System.getProperty("ecfuzz.zk.conf.path", DEFAULT_CONF_PATH);
        if (path == null || path.trim().isEmpty()) {
            return DEFAULT_CONF_PATH;
        }
        return path.trim();
    }

    private static Map<String, String> loadRuntimeConfig() throws IOException {
        Map<String, String> values = new HashMap<String, String>();
        Path confPath = Paths.get(runtimeConfPath());
        if (!Files.exists(confPath)) {
            return values;
        }
        for (String line : Files.readAllLines(confPath, StandardCharsets.UTF_8)) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                continue;
            }
            int equalsIndex = trimmed.indexOf('=');
            if (equalsIndex <= 0) {
                continue;
            }
            String key = trimmed.substring(0, equalsIndex).trim();
            String value = trimmed.substring(equalsIndex + 1).trim();
            values.put(key, value);
        }
        return values;
    }

    private static int parsePort(String value, int defaultPort) {
        if (value == null || value.trim().isEmpty()) {
            return defaultPort;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            return defaultPort;
        }
    }

    private static int parseTimeout(String value, int defaultTimeout) {
        int parsed = parsePort(value, defaultTimeout);
        return parsed > 0 ? parsed : defaultTimeout;
    }

    private static String runtimeConnectString() throws IOException {
        Map<String, String> conf = loadRuntimeConfig();
        String host = conf.get("clientPortAddress");
        if (host == null || host.trim().isEmpty() || host.trim().equals("0.0.0.0")) {
            host = "127.0.0.1";
        }
        int port = parsePort(conf.get("clientPort"), 2181);
        return host + ":" + port;
    }

    private static int runtimeTimeout() throws IOException {
        Map<String, String> conf = loadRuntimeConfig();
        int tickTime = parseTimeout(conf.get("tickTime"), 2000);
        return Math.max(1000, tickTime * 2);
    }

    public static void main(String[] args) throws Exception {
        String nodePath = "/abel";
        String sonNodePath = "/abel/son";
        String zkHost = runtimeConnectString();
        int timeOut = runtimeTimeout();
        System.out.println("Using ZooKeeper endpoint " + zkHost + " from " + runtimeConfPath());
        createConnection(zkHost, timeOut);
        creatNode(nodePath, "first-node");
        readNode(nodePath);
        if (isExists(nodePath) != null) {
            System.out.println(nodePath + " exists");
        } else {
            System.out.println(nodePath + " does not exist");
        }
        updateNode(nodePath, "updated-node");
        creatNode(sonNodePath, "child-node");
        readNode(sonNodePath);
        getChild(nodePath);
        updateNode(sonNodePath, "updated-child-node");
        deleteNode(sonNodePath);
        deleteNode(nodePath);
        closeConnection();
    }
}
