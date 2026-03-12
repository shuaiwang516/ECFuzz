package ecfuzz.agent.runtime;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

public final class TraceRuntime {
  private static final FieldBindingStore FIELD_BINDINGS = new FieldBindingStore();
  private static final ThreadLocal<Deque<FrameState>> FRAME_STACK =
      new ThreadLocal<Deque<FrameState>>() {
        @Override
        protected Deque<FrameState> initialValue() {
          return new ArrayDeque<FrameState>();
        }
      };
  private static final ThreadLocal<Binding> PENDING_BINDING = new ThreadLocal<Binding>();

  private static volatile boolean emitUseBacked = true;

  private TraceRuntime() {}

  public static void configure(Map<String, String> options) {
    emitUseBacked = !"false".equalsIgnoreCase(options.get("emit_use_backed"));
  }

  public static void enterMethod(String owner, String name, String desc) {
    FRAME_STACK.get().push(new FrameState(owner + "#" + name));
  }

  public static void exitMethod() {
    Deque<FrameState> frames = FRAME_STACK.get();
    if (!frames.isEmpty()) {
      frames.pop();
    }
  }

  public static void noteConfigGet(String paramName) {
    if (paramName == null || paramName.trim().isEmpty()) {
      return;
    }
    PENDING_BINDING.set(new Binding(paramName.trim(), currentMethodId()));
  }

  public static void afterLocalStore(int slot) {
    FrameState frame = currentFrame();
    if (frame == null) {
      return;
    }
    Binding pending = PENDING_BINDING.get();
    if (pending == null) {
      frame.clearLocalBinding(slot);
      return;
    }
    frame.bindLocal(slot, pending);
    EventLogger.emit(
        "PROV-LOCAL-STORE",
        "name=" + pending.paramName + " local=" + frame.getMethodId() + "#slot" + slot);
    PENDING_BINDING.remove();
  }

  public static void afterLocalLoad(int slot) {
    FrameState frame = currentFrame();
    if (frame == null) {
      return;
    }
    Binding binding = frame.getLocalBinding(slot);
    if (binding == null) {
      return;
    }
    EventLogger.emit(
        "PROV-LOCAL-TOUCH",
        "name=" + binding.paramName + " local=" + frame.getMethodId() + "#slot" + slot
            + " reader=" + frame.getMethodId());
    emitUseBacked(binding.paramName, "local-touch", frame.getMethodId());
  }

  public static void beforeFieldStore(Object target, String owner, String fieldName) {
    Binding pending = PENDING_BINDING.get();
    if (pending == null) {
      FIELD_BINDINGS.clearInstanceBinding(target, owner, fieldName);
      return;
    }
    FIELD_BINDINGS.bindInstance(target, owner, fieldName, pending);
    EventLogger.emit(
        "PROV-FIELD-STORE",
        "name=" + pending.paramName + " field=" + owner + "#" + fieldName
            + " writer=" + currentMethodId());
    PENDING_BINDING.remove();
  }

  public static void beforeStaticFieldStore(String owner, String fieldName) {
    Binding pending = PENDING_BINDING.get();
    if (pending == null) {
      FIELD_BINDINGS.clearStaticBinding(owner, fieldName);
      return;
    }
    FIELD_BINDINGS.bindStatic(owner, fieldName, pending);
    EventLogger.emit(
        "PROV-FIELD-STORE",
        "name=" + pending.paramName + " field=" + owner + "#" + fieldName
            + " writer=" + currentMethodId());
    PENDING_BINDING.remove();
  }

  public static void beforeFieldRead(Object target, String owner, String fieldName) {
    Binding binding = FIELD_BINDINGS.getInstanceBinding(target, owner, fieldName);
    if (binding == null) {
      return;
    }
    String site = currentMethodId();
    EventLogger.emit(
        "PROV-FIELD-TOUCH",
        "name=" + binding.paramName + " field=" + owner + "#" + fieldName + " reader=" + site);
    emitUseBacked(binding.paramName, "field-touch", site);
  }

  public static void beforeStaticFieldRead(String owner, String fieldName) {
    Binding binding = FIELD_BINDINGS.getStaticBinding(owner, fieldName);
    if (binding == null) {
      return;
    }
    String site = currentMethodId();
    EventLogger.emit(
        "PROV-FIELD-TOUCH",
        "name=" + binding.paramName + " field=" + owner + "#" + fieldName + " reader=" + site);
    emitUseBacked(binding.paramName, "field-touch", site);
  }

  public static void noteDirectUse(String opcodeName) {
    Binding pending = PENDING_BINDING.get();
    if (pending == null) {
      return;
    }
    String site = currentMethodId();
    EventLogger.emit(
        "PROV-DIRECT-USE",
        "name=" + pending.paramName + " site=" + site + " op=" + opcodeName);
    emitUseBacked(pending.paramName, "direct", site);
    PENDING_BINDING.remove();
  }

  public static void beforeMethodCall(String owner, String name, String desc) {
    Binding pending = PENDING_BINDING.get();
    if (pending == null) {
      return;
    }
    String site = currentMethodId();
    EventLogger.emit(
        "PROV-ARG-PASS",
        "name=" + pending.paramName + " caller=" + site + " callee=" + owner + "#" + name);
    emitUseBacked(pending.paramName, "arg-pass", site);
    PENDING_BINDING.remove();
  }

  private static void emitUseBacked(String paramName, String reason, String site) {
    if (!emitUseBacked) {
      return;
    }
    EventLogger.emit(
        "USE-BACKED-EXERCISED",
        "name=" + paramName + " reason=" + reason + " site=" + site);
  }

  private static FrameState currentFrame() {
    Deque<FrameState> frames = FRAME_STACK.get();
    return frames.isEmpty() ? null : frames.peek();
  }

  private static String currentMethodId() {
    FrameState frame = currentFrame();
    return frame == null ? "unknown#unknown" : frame.getMethodId();
  }

  static final class Binding {
    private final String paramName;
    private final String sourceMethod;

    Binding(String paramName, String sourceMethod) {
      this.paramName = paramName;
      this.sourceMethod = sourceMethod;
    }
  }
}
