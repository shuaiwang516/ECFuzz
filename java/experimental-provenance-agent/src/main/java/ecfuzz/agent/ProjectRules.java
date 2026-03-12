package ecfuzz.agent;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class ProjectRules {
  private final List<String> allowPrefixes;
  private final List<String> denyPrefixes;

  public ProjectRules(Map<String, String> options) {
    this.allowPrefixes = parseAllowPrefixes(options);
    this.denyPrefixes = parsePrefixes(options.get("deny"));
  }

  public boolean isAllowedClass(String internalName) {
    if (internalName == null) {
      return false;
    }
    if (internalName.startsWith("java/")
        || internalName.startsWith("javax/")
        || internalName.startsWith("sun/")
        || internalName.startsWith("jdk/")
        || internalName.startsWith("org/slf4j/")
        || internalName.startsWith("org/apache/log4j/")
        || internalName.startsWith("org/apache/commons/logging/")
        || internalName.startsWith("ecfuzz/agent/")) {
      return false;
    }
    for (String prefix : denyPrefixes) {
      if (internalName.startsWith(prefix)) {
        return false;
      }
    }
    for (String prefix : allowPrefixes) {
      if (internalName.startsWith(prefix)) {
        return true;
      }
    }
    return false;
  }

  public static String dotName(String internalName) {
    return internalName == null ? "" : internalName.replace('/', '.');
  }

  private static List<String> parseAllowPrefixes(Map<String, String> options) {
    String configuredAllow = options.get("allow");
    List<String> prefixes = parsePrefixes(configuredAllow);
    if (!prefixes.isEmpty()) {
      return prefixes;
    }

    String project = options.get("project");
    if ("hadoop-common".equals(project) || "hadoop-hdfs".equals(project)) {
      prefixes.add("org/apache/hadoop/");
    } else if ("hbase".equals(project)) {
      prefixes.add("org/apache/hadoop/hbase/");
      prefixes.add("org/apache/hadoop/");
    } else if ("zookeeper".equals(project)) {
      prefixes.add("org/apache/zookeeper/");
    } else if ("alluxio".equals(project)) {
      prefixes.add("alluxio/");
    }
    return prefixes;
  }

  private static List<String> parsePrefixes(String raw) {
    List<String> prefixes = new ArrayList<String>();
    if (raw == null || raw.trim().isEmpty()) {
      return prefixes;
    }
    for (String prefix : raw.split(";")) {
      String trimmed = prefix.trim();
      if (!trimmed.isEmpty()) {
        prefixes.add(trimmed);
      }
    }
    return prefixes;
  }
}
