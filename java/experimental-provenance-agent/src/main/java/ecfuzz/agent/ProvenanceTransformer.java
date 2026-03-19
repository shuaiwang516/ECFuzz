package ecfuzz.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.commons.AdviceAdapter;
import org.objectweb.asm.commons.Method;

import java.io.IOException;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.security.ProtectionDomain;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Map;

public final class ProvenanceTransformer implements ClassFileTransformer {
  private static final Type TRACE_RUNTIME_TYPE = Type.getType("Lecfuzz/agent/runtime/TraceRuntime;");
  private static final Method ENTER_METHOD =
      new Method("enterMethod", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");
  private static final Method EXIT_METHOD =
      new Method("exitMethod", "()V");
  private static final Method AFTER_LOCAL_STORE =
      new Method("afterLocalStore", "(I)V");
  private static final Method AFTER_LOCAL_LOAD =
      new Method("afterLocalLoad", "(I)V");
  private static final Method BEFORE_FIELD_STORE =
      new Method("beforeFieldStore", "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V");
  private static final Method BEFORE_STATIC_FIELD_STORE =
      new Method("beforeStaticFieldStore", "(Ljava/lang/String;Ljava/lang/String;)V");
  private static final Method BEFORE_FIELD_READ =
      new Method("beforeFieldRead", "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V");
  private static final Method BEFORE_STATIC_FIELD_READ =
      new Method("beforeStaticFieldRead", "(Ljava/lang/String;Ljava/lang/String;)V");
  private static final Method NOTE_DIRECT_USE =
      new Method("noteDirectUse", "(Ljava/lang/String;)V");
  private static final Method BEFORE_METHOD_CALL =
      new Method("beforeMethodCall", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");

  private final ProjectRules rules;
  private static volatile boolean debugEnabled;

  public ProvenanceTransformer(Map<String, String> options) {
    this.rules = new ProjectRules(options);
  }

  static void configureDebug(Map<String, String> options) {
    debugEnabled = "true".equalsIgnoreCase(options.get("debug_transform"));
  }

  @Override
  public byte[] transform(
      ClassLoader loader,
      String className,
      Class<?> classBeingRedefined,
      ProtectionDomain protectionDomain,
      byte[] classfileBuffer
  ) throws IllegalClassFormatException {
    if (!rules.isAllowedClass(className)) {
      return null;
    }
    try {
      debug("transform-start", className, null);
      ClassReader reader = new ClassReader(classfileBuffer);
      ClassWriter writer = new SafeClassWriter(
          reader,
          ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS,
          loader
      );
      ClassVisitor visitor = new ProvenanceClassVisitor(writer, className, rules);
      reader.accept(visitor, ClassReader.EXPAND_FRAMES);
      debug("transform-ok", className, null);
      return writer.toByteArray();
    } catch (Throwable error) {
      debug("transform-fail", className, error);
      return null;
    }
  }

  private static void debug(String stage, String className, Throwable error) {
    if (!debugEnabled) {
      return;
    }
    StringBuilder message = new StringBuilder("[CTEST][PROV-DEBUG] ");
    message.append(stage).append(" class=").append(ProjectRules.dotName(className));
    if (error != null) {
      message.append(" error=").append(error.getClass().getName())
          .append(":").append(error.getMessage());
    }
    System.err.println(message.toString());
  }

  private static final class ProvenanceClassVisitor extends ClassVisitor {
    private final String className;
    private final ProjectRules rules;

    private ProvenanceClassVisitor(ClassVisitor delegate, String className, ProjectRules rules) {
      super(Opcodes.ASM9, delegate);
      this.className = className;
      this.rules = rules;
    }

    @Override
    public MethodVisitor visitMethod(
        int access,
        String name,
        String descriptor,
        String signature,
        String[] exceptions
    ) {
      MethodVisitor delegate = super.visitMethod(access, name, descriptor, signature, exceptions);
      if (delegate == null
          || "<init>".equals(name)
          || "<clinit>".equals(name)
          || (access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) {
        return delegate;
      }
      return new ProvenanceMethodVisitor(delegate, access, name, descriptor, className, rules);
    }
  }

  private static final class ProvenanceMethodVisitor extends AdviceAdapter {
    private final String ownerInternalName;
    private final String methodName;
    private final String methodDescriptor;
    private final ProjectRules rules;

    private ProvenanceMethodVisitor(
        MethodVisitor delegate,
        int access,
        String methodName,
        String methodDescriptor,
        String ownerInternalName,
        ProjectRules rules
    ) {
      super(Opcodes.ASM9, delegate, access, methodName, methodDescriptor);
      this.ownerInternalName = ownerInternalName;
      this.methodName = methodName;
      this.methodDescriptor = methodDescriptor;
      this.rules = rules;
    }

    @Override
    protected void onMethodEnter() {
      push(ProjectRules.dotName(ownerInternalName));
      push(methodName);
      push(methodDescriptor);
      invokeStatic(TRACE_RUNTIME_TYPE, ENTER_METHOD);
    }

    @Override
    protected void onMethodExit(int opcode) {
      invokeStatic(TRACE_RUNTIME_TYPE, EXIT_METHOD);
    }

    @Override
    public void visitVarInsn(int opcode, int var) {
      super.visitVarInsn(opcode, var);
      if (isStoreOpcode(opcode)) {
        push(var);
        invokeStatic(TRACE_RUNTIME_TYPE, AFTER_LOCAL_STORE);
      } else if (isLoadOpcode(opcode)) {
        push(var);
        invokeStatic(TRACE_RUNTIME_TYPE, AFTER_LOCAL_LOAD);
      }
    }

    @Override
    public void visitJumpInsn(int opcode, Label label) {
      if (isDirectUseJump(opcode)) {
        push(opcodeName(opcode));
        invokeStatic(TRACE_RUNTIME_TYPE, NOTE_DIRECT_USE);
      }
      super.visitJumpInsn(opcode, label);
    }

    @Override
    public void visitTableSwitchInsn(int min, int max, Label dflt, Label... labels) {
      push("TABLESWITCH");
      invokeStatic(TRACE_RUNTIME_TYPE, NOTE_DIRECT_USE);
      super.visitTableSwitchInsn(min, max, dflt, labels);
    }

    @Override
    public void visitLookupSwitchInsn(Label dflt, int[] keys, Label[] labels) {
      push("LOOKUPSWITCH");
      invokeStatic(TRACE_RUNTIME_TYPE, NOTE_DIRECT_USE);
      super.visitLookupSwitchInsn(dflt, keys, labels);
    }

    @Override
    public void visitMethodInsn(int opcode, String owner, String name, String descriptor, boolean isInterface) {
      if (!"<init>".equals(name) && !"<clinit>".equals(name) && rules.isAllowedClass(owner)) {
        push(ProjectRules.dotName(owner));
        push(name);
        push(descriptor);
        invokeStatic(TRACE_RUNTIME_TYPE, BEFORE_METHOD_CALL);
      }
      super.visitMethodInsn(opcode, owner, name, descriptor, isInterface);
    }

    @Override
    public void visitFieldInsn(int opcode, String owner, String name, String descriptor) {
      if (opcode == Opcodes.GETFIELD) {
        dup();
        push(ProjectRules.dotName(owner));
        push(name);
        invokeStatic(TRACE_RUNTIME_TYPE, BEFORE_FIELD_READ);
        super.visitFieldInsn(opcode, owner, name, descriptor);
        return;
      }
      if (opcode == Opcodes.GETSTATIC) {
        push(ProjectRules.dotName(owner));
        push(name);
        invokeStatic(TRACE_RUNTIME_TYPE, BEFORE_STATIC_FIELD_READ);
        super.visitFieldInsn(opcode, owner, name, descriptor);
        return;
      }
      if (opcode == Opcodes.PUTFIELD) {
        Type valueType = Type.getType(descriptor);
        Type ownerType = Type.getObjectType(owner);
        int valueLocal = newLocal(valueType);
        int ownerLocal = newLocal(ownerType);
        storeLocal(valueLocal, valueType);
        storeLocal(ownerLocal, ownerType);
        loadLocal(ownerLocal, ownerType);
        push(ProjectRules.dotName(owner));
        push(name);
        invokeStatic(TRACE_RUNTIME_TYPE, BEFORE_FIELD_STORE);
        loadLocal(ownerLocal, ownerType);
        loadLocal(valueLocal, valueType);
        super.visitFieldInsn(opcode, owner, name, descriptor);
        return;
      }
      if (opcode == Opcodes.PUTSTATIC) {
        Type valueType = Type.getType(descriptor);
        int valueLocal = newLocal(valueType);
        storeLocal(valueLocal, valueType);
        push(ProjectRules.dotName(owner));
        push(name);
        invokeStatic(TRACE_RUNTIME_TYPE, BEFORE_STATIC_FIELD_STORE);
        loadLocal(valueLocal, valueType);
        super.visitFieldInsn(opcode, owner, name, descriptor);
        return;
      }
      super.visitFieldInsn(opcode, owner, name, descriptor);
    }

    private static boolean isStoreOpcode(int opcode) {
      return opcode == Opcodes.ISTORE
          || opcode == Opcodes.LSTORE
          || opcode == Opcodes.FSTORE
          || opcode == Opcodes.DSTORE
          || opcode == Opcodes.ASTORE;
    }

    private static boolean isLoadOpcode(int opcode) {
      return opcode == Opcodes.ILOAD
          || opcode == Opcodes.LLOAD
          || opcode == Opcodes.FLOAD
          || opcode == Opcodes.DLOAD
          || opcode == Opcodes.ALOAD;
    }

    private static boolean isDirectUseJump(int opcode) {
      return opcode == Opcodes.IFEQ
          || opcode == Opcodes.IFNE
          || opcode == Opcodes.IFLT
          || opcode == Opcodes.IFGE
          || opcode == Opcodes.IFGT
          || opcode == Opcodes.IFLE
          || opcode == Opcodes.IF_ICMPEQ
          || opcode == Opcodes.IF_ICMPNE
          || opcode == Opcodes.IF_ICMPLT
          || opcode == Opcodes.IF_ICMPGE
          || opcode == Opcodes.IF_ICMPGT
          || opcode == Opcodes.IF_ICMPLE
          || opcode == Opcodes.IF_ACMPEQ
          || opcode == Opcodes.IF_ACMPNE
          || opcode == Opcodes.IFNULL
          || opcode == Opcodes.IFNONNULL;
    }

  private static String opcodeName(int opcode) {
      switch (opcode) {
        case Opcodes.IFEQ:
          return "IFEQ";
        case Opcodes.IFNE:
          return "IFNE";
        case Opcodes.IFLT:
          return "IFLT";
        case Opcodes.IFGE:
          return "IFGE";
        case Opcodes.IFGT:
          return "IFGT";
        case Opcodes.IFLE:
          return "IFLE";
        case Opcodes.IF_ICMPEQ:
          return "IF_ICMPEQ";
        case Opcodes.IF_ICMPNE:
          return "IF_ICMPNE";
        case Opcodes.IF_ICMPLT:
          return "IF_ICMPLT";
        case Opcodes.IF_ICMPGE:
          return "IF_ICMPGE";
        case Opcodes.IF_ICMPGT:
          return "IF_ICMPGT";
        case Opcodes.IF_ICMPLE:
          return "IF_ICMPLE";
        case Opcodes.IF_ACMPEQ:
          return "IF_ACMPEQ";
        case Opcodes.IF_ACMPNE:
          return "IF_ACMPNE";
        case Opcodes.IFNULL:
          return "IFNULL";
        case Opcodes.IFNONNULL:
          return "IFNONNULL";
        default:
          return "OP-" + opcode;
      }
    }
  }

  private static final class SafeClassWriter extends ClassWriter {
    private final TypeHierarchyResolver resolver;

    private SafeClassWriter(ClassReader reader, int flags, ClassLoader loader) {
      super(reader, flags);
      this.resolver = new TypeHierarchyResolver(loader);
    }

    @Override
    protected String getCommonSuperClass(String type1, String type2) {
      try {
        return resolver.getCommonSuperClass(type1, type2);
      } catch (Throwable ignored) {
        return "java/lang/Object";
      }
    }
  }

  private static final class TypeHierarchyResolver {
    private final ClassLoader loader;
    private final ConcurrentHashMap<String, ClassInfo> cache =
        new ConcurrentHashMap<String, ClassInfo>();

    private TypeHierarchyResolver(ClassLoader loader) {
      this.loader = loader;
    }

    private String getCommonSuperClass(String type1, String type2) {
      if (type1 == null || type2 == null) {
        return "java/lang/Object";
      }
      if (type1.equals(type2)) {
        return type1;
      }

      if (isAssignableFrom(type1, type2)) {
        return type1;
      }
      if (isAssignableFrom(type2, type1)) {
        return type2;
      }

      ClassInfo type1Info = getClassInfo(type1);
      ClassInfo type2Info = getClassInfo(type2);
      if (type1Info == null || type2Info == null) {
        String reflected = getCommonSuperClassFromReflectionIfSafe(type1, type2);
        if (reflected != null) {
          return reflected;
        }
        return "java/lang/Object";
      }
      if (type1Info.isInterface || type2Info.isInterface) {
        return "java/lang/Object";
      }

      String current = type1Info.superName;
      while (current != null) {
        if (isAssignableFrom(current, type2)) {
          return current;
        }
        ClassInfo currentInfo = getClassInfo(current);
        if (currentInfo == null) {
          break;
        }
        current = currentInfo.superName;
      }
      return "java/lang/Object";
    }

    private String getCommonSuperClassFromReflectionIfSafe(String type1, String type2) {
      if (!isPlatformClass(type1) || !isPlatformClass(type2)) {
        return null;
      }
      return getCommonSuperClassFromReflection(type1, type2);
    }

    private String getCommonSuperClassFromReflection(String type1, String type2) {
      try {
        Class<?> class1 = loadRuntimeClass(type1);
        Class<?> class2 = loadRuntimeClass(type2);
        if (class1 == null || class2 == null) {
          return null;
        }
        if (class1.isAssignableFrom(class2)) {
          return Type.getInternalName(class1);
        }
        if (class2.isAssignableFrom(class1)) {
          return Type.getInternalName(class2);
        }
        if (class1.isInterface() || class2.isInterface()) {
          return "java/lang/Object";
        }
        Class<?> current = class1.getSuperclass();
        while (current != null && !current.isAssignableFrom(class2)) {
          current = current.getSuperclass();
        }
        return current == null ? "java/lang/Object" : Type.getInternalName(current);
      } catch (Throwable ignored) {
        return null;
      }
    }

    private Class<?> loadRuntimeClass(String internalName) throws ClassNotFoundException {
      String binaryName = toBinaryName(internalName);
      ClassLoader preferredLoader = loader;
      if (preferredLoader == null) {
        preferredLoader = Thread.currentThread().getContextClassLoader();
      }
      if (preferredLoader != null) {
        return Class.forName(binaryName, false, preferredLoader);
      }
      return Class.forName(binaryName, false, ProvenanceTransformer.class.getClassLoader());
    }

    private boolean isPlatformClass(String internalName) {
      return internalName.startsWith("java/")
          || internalName.startsWith("javax/")
          || internalName.startsWith("jdk/")
          || internalName.startsWith("sun/")
          || internalName.startsWith("com/sun/")
          || internalName.startsWith("org/w3c/")
          || internalName.startsWith("org/xml/");
    }

    private boolean isAssignableFrom(String target, String source) {
      if (target.equals(source) || "java/lang/Object".equals(target)) {
        return true;
      }
      ClassInfo sourceInfo = getClassInfo(source);
      if (sourceInfo == null) {
        return false;
      }
      for (String interfaceName : sourceInfo.interfaces) {
        if (target.equals(interfaceName) || isAssignableFrom(target, interfaceName)) {
          return true;
        }
      }
      String superName = sourceInfo.superName;
      while (superName != null) {
        if (target.equals(superName)) {
          return true;
        }
        ClassInfo superInfo = getClassInfo(superName);
        if (superInfo == null) {
          break;
        }
        for (String interfaceName : superInfo.interfaces) {
          if (target.equals(interfaceName) || isAssignableFrom(target, interfaceName)) {
            return true;
          }
        }
        superName = superInfo.superName;
      }
      return false;
    }

    private ClassInfo getClassInfo(String internalName) {
      if (internalName == null || internalName.startsWith("[")) {
        return null;
      }
      ClassInfo cached = cache.get(internalName);
      if (cached != null) {
        return cached;
      }
      ClassInfo loaded = loadClassInfo(internalName);
      if (loaded == null) {
        return null;
      }
      ClassInfo previous = cache.putIfAbsent(internalName, loaded);
      return previous == null ? loaded : previous;
    }

    private ClassInfo loadClassInfo(String internalName) {
      InputStream stream = null;
      try {
        String resourceName = internalName + ".class";
        if (loader != null) {
          stream = loader.getResourceAsStream(resourceName);
        }
        if (stream == null) {
          ClassLoader contextLoader = Thread.currentThread().getContextClassLoader();
          if (contextLoader != null) {
            stream = contextLoader.getResourceAsStream(resourceName);
          }
        }
        if (stream == null) {
          stream = ClassLoader.getSystemResourceAsStream(resourceName);
        }
        if (stream == null) {
          return null;
        }
        ClassReader reader = new ClassReader(stream);
        return new ClassInfo(
            (reader.getAccess() & Opcodes.ACC_INTERFACE) != 0,
            reader.getSuperName(),
            reader.getInterfaces()
        );
      } catch (IOException ignored) {
        return null;
      } finally {
        if (stream != null) {
          try {
            stream.close();
          } catch (IOException ignored) {
            // best effort cleanup only
          }
        }
      }
    }

    private String toBinaryName(String internalName) {
      if (internalName.startsWith("[")) {
        return internalName.replace('/', '.');
      }
      return internalName.replace('/', '.');
    }
  }

  private static final class ClassInfo {
    private final boolean isInterface;
    private final String superName;
    private final String[] interfaces;

    private ClassInfo(boolean isInterface, String superName, String[] interfaces) {
      this.isInterface = isInterface;
      this.superName = superName;
      this.interfaces = interfaces == null ? new String[0] : interfaces;
    }
  }
}
