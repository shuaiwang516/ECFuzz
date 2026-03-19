package ecfuzz.fixture;

import ecfuzz.agent.runtime.TraceRuntime;

import java.io.IOException;

public final class FixtureMain {
  private String boundField;
  private static String staticBoundField;
  private static int sink;
  private static final ThrowableSink THROWABLE_SINK = new ThrowableSink() {
    @Override
    public void accept(String message, Throwable throwable) {
      if (message != null && throwable != null) {
        sink += message.length() + throwable.getClass().getSimpleName().length();
      }
    }
  };

  public static void main(String[] args) {
    String mode = args.length == 0 ? "direct" : args[0];
    FixtureMain fixture = new FixtureMain();
    if ("direct".equals(mode)) {
      fixture.runDirect();
    } else if ("field".equals(mode)) {
      fixture.runField();
    } else if ("local".equals(mode)) {
      fixture.runLocal();
    } else if ("arg".equals(mode)) {
      fixture.runArg();
    } else if ("static-field".equals(mode)) {
      fixture.runStaticField();
    } else if ("throwable-merge".equals(mode)) {
      fixture.runThrowableMerge(args.length > 1);
    } else {
      throw new IllegalArgumentException("unknown mode: " + mode);
    }
    System.out.println("sink=" + sink);
  }

  private static String source(String paramName, String value) {
    TraceRuntime.noteConfigGet(paramName);
    return value;
  }

  private void runDirect() {
    if (source("fixture.direct", "value") != null) {
      sink++;
    }
  }

  private void runField() {
    boundField = source("fixture.field", "value");
    if (boundField != null) {
      sink++;
    }
  }

  private void runLocal() {
    String localValue = source("fixture.local", "value");
    if (localValue != null) {
      sink++;
    }
  }

  private void runArg() {
    consume(source("fixture.arg", "value"));
  }

  private void runStaticField() {
    staticBoundField = source("fixture.static", "value");
    if (staticBoundField != null) {
      sink++;
    }
  }

  private void runThrowableMerge(boolean firstBranch) {
    Throwable throwable;
    try {
      if (firstBranch) {
        throw new IOException("branch-a");
      }
      throw new IllegalArgumentException("branch-b");
    } catch (IOException error) {
      throwable = error;
    } catch (RuntimeException error) {
      throwable = error;
    }
    THROWABLE_SINK.accept(source("fixture.throwable", "value"), throwable);
  }

  private void consume(String value) {
    if (value != null) {
      sink += value.length();
    }
  }

  private interface ThrowableSink {
    void accept(String message, Throwable throwable);
  }
}
