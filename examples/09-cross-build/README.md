# 09: Cross-Build For ARM64

Goal: build an AArch64 Linux program in the controlled x86_64 container and
inspect its compiler, profiles and ELF files. **This lesson only builds and
inspects artifacts. It does not run target programs, install packages or deploy
anything.** A target device and an installed deployment runtime are not required
for these checks.

## Execution And Target

| Role | CPU / tool |
| --- | --- |
| Build machine running Bazel, CMake, Conan and the cross compiler | Linux x86_64 |
| Conan `build` profile | `arch=x86_64`, native GCC 13 |
| Conan `host` profile (the dependency's target, not the build machine) | `arch=armv8`, AArch64 GCC 13 |
| Program and static libraries produced by the build | ELF64 AArch64 |

Use the complete `linux_x86_64_cross_arm64` preset, not independent platform or
compiler overrides. It selects the native-rule toolchain, CMake toolchain and
Conan profiles together. An x86_64 compiler executable can emit ARM64 objects;
its own ELF machine is not the target machine.

## Files And Targets

| File/target | Role |
| --- | --- |
| `app/main.cc` | Native Bazel consumer of a real out-of-line function |
| `CMakeLists.txt`, `include/cross_math/answer.h`, `src/answer.cc` | Static wrapper library built by CMake |
| `conanfile.txt`, `conan.lock` | Reviewed, pinned `tiny_math/1.0` dependency |
| `//_support:recipe_index` | Shared source-only recipe infrastructure, not another lesson's output |
| `//09-cross-build:answer` | CMake library plus the compiled Conan dependency |
| `//09-cross-build:answer_conan` | Declared Conan snapshot and identity manifest |
| `//09-cross-build:app` | Linked ARM64 program |

The code computes `20 * 2 + 1`, but this lesson does not execute it or claim a
runtime result. The link and symbol checks demonstrate that both libraries are
real compiled inputs. CMake's `install` step only stages files into Bazel's
declared build outputs; it does not install them on the build system or a device.
The checker neither installs toolchains nor modifies the system or target runtime.

## Build

Working directory: `forge/examples`. The existing Linux/amd64 image includes
`gcc-13-aarch64-linux-gnu`, `g++-13-aarch64-linux-gnu` and ARM64 development
libraries. Keep using the shared workspace and output base.

```bash
../forge-bazel build --config=linux_x86_64_cross_arm64 --config=debug \
  //09-cross-build:app
../forge-bazel build --config=linux_x86_64_cross_arm64 --config=release \
  //09-cross-build:app
```

Both commands must exit zero. The program is `bazel-bin/09-cross-build/app` for
the most recent build configuration. To build just the libraries, use
`//09-cross-build:answer` with the same options. Do not use `bazel run` or execute
the ARM64 binary in the x86_64 container.

## Inspect Without Running

From `forge/examples`, enter `../forge-shell`, then use these read-only tools:

```bash
aarch64-linux-gnu-gcc-13 -dumpmachine
aarch64-linux-gnu-gcc-13 -print-sysroot
aarch64-linux-gnu-gcc-13 -print-search-dirs
aarch64-linux-gnu-readelf -hW bazel-bin/09-cross-build/app
aarch64-linux-gnu-readelf -lW bazel-bin/09-cross-build/app
aarch64-linux-gnu-readelf -dW bazel-bin/09-cross-build/app
aarch64-linux-gnu-nm -C --defined-only bazel-bin/09-cross-build/app
```

Expect `aarch64-linux-gnu`, `Machine: AArch64`, the interpreter
`/opt/eros/lib/ld-linux-aarch64.so.1`, and `/opt/eros/lib` in RUNPATH. The defined
symbols include `cross_math::transform(int)` and `tiny_math::transform(int)`.

Compiler-default sysroot, header/library search paths and the ELF interpreter
are different concepts. The compiler may report `/` as its configured sysroot
while using its ARM64 cross-development directories. `/opt/eros` is Forge's
deployment loader/RUNPATH convention, not automatically a full compiler sysroot.
A path recorded in ELF does not prove the loader is installed or ABI-compatible.
Missing deployment runtime does not prevent this build-only lesson from passing.

## Verify The Build

Inside `../forge-shell`, still in `forge/examples`:

```bash
python3 09-cross-build/check.py
```

`--mode debug` or `--mode release` selects one mode. The checker builds explicit
targets, resolves artifacts with configured queries rather than relying on the
mutable `bazel-bin` link, and checks:

- AArch64 machine headers for the program and both static libraries.
- The interpreter, RUNPATH and linked business/dependency symbols.
- The captured environment identity, actual compiler target/version/sysroot,
  header/library search paths and native-rule compile/link command arguments.
- Separate x86_64 build and ARM64 host profiles, matching profile hashes, lock
  identity, source-built dependency architecture and build mode.
- Unchanged lesson sources, shared recipe inputs and workspace locks.

The ignored report is `.forge-evidence/09-cross-build.json`. `PASS` means only
that building and static inspection succeeded; it always records target
execution as `NOT_RUN` and deployment as `NOT_PERFORMED`, even if a runtime is
present. This lesson creates no deb, exports no deployment runtime and uses no
emulator or remote device. Follow the [workspace cleanup guide](../README.md#resources-and-cleanup)
only when the shared build cache is no longer needed.
