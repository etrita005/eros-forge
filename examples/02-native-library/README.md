# 02: Consume A Native Library

Goal: move the same computation into a real compiled library, then consume it
from a standard `rules_cc` binary. Prerequisites are the native environment in
the [workspace guide](../README.md); lesson 01 need not have been built.

## Files And Targets

| File/target | Role |
| --- | --- |
| `include/native_math/answer.h` | Public declaration, not an inline implementation |
| `src/answer.cc` | Out-of-line implementation in a static library |
| `app/main.cc` | Consumer in a separate directory |
| `//02-native-library:answer` | `eros_cc_library`, explicitly static |
| `//02-native-library:app` | Plain `cc_binary`, depending only on `:answer` |

`strip_include_prefix = "include"` publishes `native_math/answer.h` as the include
name. The consumer adds no `includes`, `copts`, `linkopts`, or library paths.
Its sole dependency supplies compilation and linking information through `CcInfo`.
`linkstatic = True` keeps shared-library deployment out of this lesson.

## Build

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`. From the Forge repository root, enter it once:

```bash
cd examples
```

If already inside `examples/02-native-library`, use `cd ..` instead. Build the
consumer and its library dependency without executing the program:

```bash
bazel build --config=debug //02-native-library:app
bazel build --config=release //02-native-library:app
```

To build only the library:

```bash
bazel build --config=debug //02-native-library:answer
bazel build --config=release //02-native-library:answer
```

Each command must exit zero with `Build completed successfully`. Building `:app`
produces `bazel-bin/02-native-library/app`; building `:answer` alone does not
build the consumer. Use the configured output query
below to locate the library files rather than guessing an internal archive name.
Do not clean between configurations.

## Run

From the same `forge/examples` directory:

```bash
bazel run --config=debug //02-native-library:app
bazel run --config=release //02-native-library:app
```

Both commands must print `result=41` and exit zero. The value comes from the
library's compiled function, not a header-only implementation.

## Inspect And Clean Up

```bash
bazel cquery --config=debug //02-native-library:answer --output=files
bazel query 'deps(//02-native-library:app, 1)'
bazel aquery 'mnemonic("CppLink", //02-native-library:app)' --config=debug
```

Inspect the explicit library dependency and the native link action. Header and
archive paths are provider outputs, not manual consumer flags.

Do not edit or clear the user Conan cache. Reuse this workspace/output base for
the remaining lessons; [workspace cleanup](../README.md#resources-and-cleanup)
applies only after diagnostics have been saved.
