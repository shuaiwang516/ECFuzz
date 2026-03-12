package ecfuzz.agent.runtime;

import java.util.HashMap;
import java.util.Map;

final class FrameState {
  private final String methodId;
  private final Map<Integer, TraceRuntime.Binding> localBindings = new HashMap<Integer, TraceRuntime.Binding>();

  FrameState(String methodId) {
    this.methodId = methodId;
  }

  String getMethodId() {
    return methodId;
  }

  void bindLocal(int slot, TraceRuntime.Binding binding) {
    localBindings.put(slot, binding);
  }

  TraceRuntime.Binding getLocalBinding(int slot) {
    return localBindings.get(slot);
  }

  void clearLocalBinding(int slot) {
    localBindings.remove(slot);
  }
}
