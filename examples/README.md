# Forge Beginner Examples

This is one consuming Bazel workspace. Run all lesson commands from this
directory. `MODULE.bazel` resolves the Forge checkout at `..`; `.bazelrc`
imports its configuration and bounds outer/internal parallelism to two jobs.
Rules loaded directly from `rules_cc` have an explicit module dependency.

## Prerequisites

Use Forge's controlled Linux x86_64 or ARM64 build environment with GCC 13,
binutils, CMake, Make, Python and Conan. Native selection is automatic; explicit
presets must match the execution host. See the [Forge guide](../README.md).

The native introductory path does not require GDB, a robot, a cross SDK, a
Conan server or a remote cache. Initial Bazel module resolution can need access
to the configured module registries; this is separate from the source-only
Conan recipe index.

## Build

From the Forge repository root, enter the shared workspace once:

```bash
cd examples
```

Build all four introductory programs without executing them:

```bash
bazel build --config=debug \
  //01-minimal-app:app //02-native-library:app \
  //03-cmake-library:app //04-conan-locked:app

bazel build --config=release \
  //01-minimal-app:app //02-native-library:app \
  //03-cmake-library:app //04-conan-locked:app
```

Each build must exit zero with `Build completed successfully`. Executables are
under `bazel-bin/<lesson>/app`. `bazel build` builds dependencies but does not run
the programs; `bazel run` builds and then runs one program. Each lesson README
provides its own program and, where applicable, library-only build commands.
Do not clean or create extra output bases between configurations.

## Lessons

| Lesson | Target | State |
| --- | --- | --- |
| [01 Minimal app](01-minimal-app/README.md) | `//01-minimal-app:app` | Implemented |
| [02 Native library](02-native-library/README.md) | `//02-native-library:app` | Implemented |
| [03 CMake library](03-cmake-library/README.md) | `//03-cmake-library:app` | Implemented |
| [04 Locked Conan dependency](04-conan-locked/README.md) | `//04-conan-locked:app` | Implemented |

Each program computes `result=41` through a different build path and must
exit zero. Lesson packages do not consume another lesson's generated output.
The [example plan](../documents/examples-plan.md) defines subsequent batches;
lessons 05-10 are not implemented here.

## Verify The Introductory Batch

```bash
python3 check.py
```

This builds explicit targets and runs all four native programs in Debug and
Release without cleaning or creating extra output bases. `--mode debug` or
`--mode release` selects a smaller run. Every program must exit zero with exactly
`result=41`. The check also verifies the source-only Conan snapshot, variant,
reviewed Conan/module locks, removed private home, unchanged source inputs and user-cache
metadata. It does not read/hash the cached package payloads; each cache audit
has a 30-second deadline.

The default report/logs are ignored under `.forge-evidence/`; `--report PATH`
selects another report. These are native example checks, not cross-platform,
target deployment or remote-cache acceptance. No test command uses wildcard
selection or hides a failing exit code.

## Resources And Cleanup

Reuse the default output base for this workspace across lessons and build modes.
Do not create one output base per lesson. Tool inputs and sandbox directories
can consume substantial inodes even when byte capacity remains available.

Use `bazel info output_base` to identify this workspace's cache. Archive any
needed diagnostics first. `bazel shutdown` stops the server but retains files;
`bazel clean --expunge` removes this workspace's output base. Do not remove user
Conan caches or unrelated workspaces as lesson cleanup.
