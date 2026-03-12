package ecfuzz.agent.runtime;

final class EventLogger {
  private EventLogger() {}

  static synchronized void emit(String eventType, String payload) {
    System.err.println("[CTEST][" + eventType + "] " + payload);
  }
}
