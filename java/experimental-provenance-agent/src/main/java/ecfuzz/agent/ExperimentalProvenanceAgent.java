package ecfuzz.agent;

import ecfuzz.agent.runtime.TraceRuntime;

import java.io.File;
import java.lang.instrument.Instrumentation;
import java.net.URISyntaxException;
import java.security.CodeSource;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.jar.JarFile;

public final class ExperimentalProvenanceAgent {
  private ExperimentalProvenanceAgent() {}

  public static void premain(String agentArgs, Instrumentation inst) {
    Map<String, String> options = parseOptions(agentArgs);
    TraceRuntime.configure(options);
    ProvenanceTransformer.configureDebug(options);
    appendAgentJarToSystemSearch(inst);
    if ("noop".equalsIgnoreCase(options.getOrDefault("mode", "active"))) {
      return;
    }
    inst.addTransformer(new ProvenanceTransformer(options), false);
  }

  private static Map<String, String> parseOptions(String raw) {
    if (raw == null || raw.trim().isEmpty()) {
      return Collections.emptyMap();
    }
    Map<String, String> parsed = new HashMap<String, String>();
    for (String token : raw.split(",")) {
      String trimmed = token.trim();
      if (trimmed.isEmpty()) {
        continue;
      }
      int split = trimmed.indexOf('=');
      if (split < 0) {
        parsed.put(trimmed, "true");
      } else {
        parsed.put(trimmed.substring(0, split), trimmed.substring(split + 1));
      }
    }
    return parsed;
  }

  private static void appendAgentJarToSystemSearch(Instrumentation inst) {
    try {
      CodeSource codeSource = ExperimentalProvenanceAgent.class
          .getProtectionDomain()
          .getCodeSource();
      if (codeSource == null || codeSource.getLocation() == null) {
        return;
      }
      File location = new File(codeSource.getLocation().toURI());
      if (!location.isFile()) {
        return;
      }
      inst.appendToSystemClassLoaderSearch(new JarFile(location));
    } catch (Exception ignored) {
      // Best effort only. The source-level hooks use reflection and tolerate absence.
    }
  }
}
