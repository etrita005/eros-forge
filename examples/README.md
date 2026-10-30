# Forge Beginner Examples

This is one consuming Bazel workspace. Run all lesson commands from this
directory. `MODULE.bazel` resolves the Forge checkout at `..`; `.bazelrc`
imports its configuration and bounds outer/internal parallelism to two jobs.
Rules loaded directly from `rules_cc` have an explicit module dependency.

## Prerequisites

On the host use the local Linux/amd64 image and `../forge-bazel`; Python 3,
Docker and the Forge checkout are required, but host Bazel/GCC/CMake/Conan are
not. From `forge/examples`, `../forge-shell` enters the same container; use
`bazel` directly there. `.bazelrc` imports the Forge rc automatically. The
ARM64 native image is not available locally. See the [Forge guide](../README.md).

The native introductory path does not require GDB, a robot, a target SDK, a
Conan server or a remote cache. Initial Bazel module resolution can need access
to the configured module registries; this is separate from the source-only
Conan recipe index.

## Build

From the Forge repository root, enter the shared workspace once:

```bash
cd examples
```

Build all four Batch A programs without executing them on the host:

```bash
../forge-bazel build --config=debug \
  //01-minimal-app:app //02-native-library:app \
  //03-cmake-library:app //04-conan-locked:app

../forge-bazel build --config=release \
  //01-minimal-app:app //02-native-library:app \
  //03-cmake-library:app //04-conan-locked:app
```

Each build must exit zero with `Build completed successfully`. Executables are
under `bazel-bin/<lesson>/app`. The wrapper forwards `bazel build`, which builds
dependencies but does not run the programs; `bazel run` builds and then runs one
program. Each lesson README provides its own program and, where applicable,
library-only build commands.
Do not clean or create extra output bases between configurations.

## Lessons

| Lesson | Target | State |
| --- | --- | --- |
| [01 Minimal app](01-minimal-app/README.md) | `//01-minimal-app:app` | Implemented |
| [02 Native library](02-native-library/README.md) | `//02-native-library:app` | Implemented |
| [03 CMake library](03-cmake-library/README.md) | `//03-cmake-library:app` | Implemented |
| [04 Locked Conan dependency](04-conan-locked/README.md) | `//04-conan-locked:app` | Implemented |
| [05 Private runtime](05-private-runtime/README.md) | `//05-private-runtime:runtime_tar` | Implemented |
| [06 Debian package](06-debian-package/README.md) | `//06-debian-package:deb` | Implemented |
| 06b Two dependent debs | `//06b-deb-dependency/a:a_deb`, `//06b-deb-dependency/b:b_deb` | Implemented (native delivery extension) |
| [07 Release symbols](07-release-symbols/README.md) | `//07-release-symbols:symbols` | Implemented |
| [08 Sanitizer errors](08-sanitizer-errors/README.md) | `//08-sanitizer-errors:app` | Implemented |
| [09 Cross build](09-cross-build/README.md) | `//09-cross-build:app` | Implemented (build-only) |

Lessons 01-04 compute `result=41` through different build paths and must exit
zero. Lessons 05-08 add private runtime delivery, Debian packaging, independent
Release symbols and sanitizer controls; lesson 08 uses `forge-san=43` for its
clean control. Lesson packages do not consume another lesson's generated output.
Lesson 09 cross-builds for ARM64 and inspects artifacts without executing or
deploying them. The [example plan](../documents/examples-plan.md) defines the
remaining lesson 10. The independent 06b example covers a
two-package deployment boundary; it is not a prerequisite for lesson 06.

## Two Debian Packages: B Depends On A

From `forge/examples`, use the controlled native shell to build and check the
independent packages (the checker uses the same Bazel output base):

```bash
../forge-shell
# Inside the shell:
python3 06b-deb-dependency/check.py
```

Or build and inspect each output explicitly from the host in `forge/examples`:

```bash
../forge-bazel build --config=release //06b-deb-dependency/a:a_deb //06b-deb-dependency/b:b_deb
dpkg-deb --field bazel-bin/06b-deb-dependency/b/b_deb.deb Depends
dpkg-deb --contents bazel-bin/06b-deb-dependency/a/a_deb.deb
dpkg-deb --contents bazel-bin/06b-deb-dependency/b/b_deb.deb
```

The A library is declared as B's Bazel `deps` and has a real `libforge_example_a.so.1`
SONAME. B uses a relative RUNPATH to A's installed private library directory.
Each module writes only `pkg_eros_deb(srcs = ...)`; B declares
`depends = ["//06b-deb-dependency/a:a_deb"]`. Forge checks the selected A.deb's
payload identity, architecture and ELF against B, omits A's library from B,
and derives the versioned Debian `Depends` from A.deb's actual metadata. The checker verifies
the ELF and package contents, then runs B from an isolated extraction root with
A absent, present and removed, without `LD_LIBRARY_PATH`. It also exercises
`dpkg` installation and removal dependency checks in a separate disposable,
unprivileged root; this is not a clean target deployment or ABI acceptance test.
This sample builds A from source; selecting an older published A release in CI
requires a separately pinned artifact and matching compilation inputs.

## Verify Delivery And Diagnostics Lessons

From `forge/examples`, each implemented lesson has a checker that invokes
`bazel` directly. Enter the controlled shell once:

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 05-private-runtime/check.py
python3 06-debian-package/check.py
python3 07-release-symbols/check.py
python3 08-sanitizer-errors/check.py
```

Lesson 05 extracts the private runtime, checks the SONAME chain and runs without
`LD_LIBRARY_PATH`. Lesson 06 validates deb metadata, version precedence,
architecture and extraction. Lesson 07 validates Release symbols and a GDB
source breakpoint. Lesson 08 runs clean controls and real ASan/UBSan faults;
TSan is reported as skipped when the host cannot initialize its runtime.

## Verify Cross Builds Only

Lesson 09 uses the existing ARM64 cross tools in the x86_64 container. From
`forge/examples`:

```bash
../forge-bazel build --config=linux_x86_64_cross_arm64 --config=debug //09-cross-build:app
../forge-bazel build --config=linux_x86_64_cross_arm64 --config=release //09-cross-build:app
../forge-shell
# Inside the shell, still in forge/examples:
python3 09-cross-build/check.py
```

The checker validates ELF machine/interpreter/RUNPATH, both compiled static
libraries, actual compiler selection, separate Conan build/host profiles and
environment/lock identity. Its ignored report is
`.forge-evidence/09-cross-build.json`. This is build/static-inspection evidence
only: no deb installation, runtime provisioning, target execution or deployment
is performed. Do not use `bazel run` for this lesson's cross-built program.

## Verify The Introductory Batch

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 check.py
```

Run the checker **inside** the shell: it invokes `bazel` directly and does not
need a host-side Bazel wrapper. It builds explicit targets and runs all four
native programs in Debug and Release without cleaning or creating extra output
bases. `--mode debug` or `--mode release` selects a smaller run. Every program
must exit zero with exactly
`result=41`. The check also verifies the source-only Conan snapshot, variant,
reviewed Conan/module locks, removed private home, unchanged source inputs and user-cache
metadata. It does not read/hash the cached package payloads; each cache audit
has a 30-second deadline.

The default report/logs are ignored under `.forge-evidence/`; `--report PATH`
selects another report. These are local Linux/amd64 native example checks, not
ARM64, CI, target deployment or remote-cache acceptance. No test command uses
wildcard selection or hides a failing exit code.

## Resources And Cleanup

Reuse the default output base for this workspace across lessons and build modes.
Do not create one output base per lesson. Tool inputs and sandbox directories
can consume substantial inodes even when byte capacity remains available.

Use `../forge-bazel info output_base` to identify this workspace's cache.
Archive any needed diagnostics first. `../forge-bazel shutdown` stops the server
but retains files; `../forge-bazel clean --expunge` removes this workspace's
output base. Do not remove user Conan caches or unrelated workspaces as lesson
cleanup. Inside the shell use `bazel` in place of `../forge-bazel`.
