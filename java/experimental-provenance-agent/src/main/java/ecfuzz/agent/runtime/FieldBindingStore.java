package ecfuzz.agent.runtime;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class FieldBindingStore {
  private final Map<Object, Map<String, TraceRuntime.Binding>> instanceBindings =
      Collections.synchronizedMap(new IdentityHashMap<Object, Map<String, TraceRuntime.Binding>>());
  private final Map<String, TraceRuntime.Binding> staticBindings =
      new ConcurrentHashMap<String, TraceRuntime.Binding>();

  void bindInstance(Object target, String owner, String fieldName, TraceRuntime.Binding binding) {
    if (target == null) {
      return;
    }
    synchronized (instanceBindings) {
      Map<String, TraceRuntime.Binding> fieldMap = instanceBindings.get(target);
      if (fieldMap == null) {
        fieldMap = new ConcurrentHashMap<String, TraceRuntime.Binding>();
        instanceBindings.put(target, fieldMap);
      }
      fieldMap.put(owner + "#" + fieldName, binding);
    }
  }

  TraceRuntime.Binding getInstanceBinding(Object target, String owner, String fieldName) {
    if (target == null) {
      return null;
    }
    synchronized (instanceBindings) {
      Map<String, TraceRuntime.Binding> fieldMap = instanceBindings.get(target);
      if (fieldMap == null) {
        return null;
      }
      return fieldMap.get(owner + "#" + fieldName);
    }
  }

  void bindStatic(String owner, String fieldName, TraceRuntime.Binding binding) {
    staticBindings.put(owner + "#" + fieldName, binding);
  }

  TraceRuntime.Binding getStaticBinding(String owner, String fieldName) {
    return staticBindings.get(owner + "#" + fieldName);
  }

  void clearInstanceBinding(Object target, String owner, String fieldName) {
    if (target == null) {
      return;
    }
    synchronized (instanceBindings) {
      Map<String, TraceRuntime.Binding> fieldMap = instanceBindings.get(target);
      if (fieldMap == null) {
        return;
      }
      fieldMap.remove(owner + "#" + fieldName);
    }
  }

  void clearStaticBinding(String owner, String fieldName) {
    staticBindings.remove(owner + "#" + fieldName);
  }
}
