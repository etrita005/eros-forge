# 03: Export A CMake Library

Goal: build the same compiled-library interface with CMake and consume it from a
plain Bazel `cc_binary`. Only the controlled native environment in the
[workspace guide](../README.md) is required.

## Files And Targets

| File/target | Role |
| --- | --- |
| `CMakeLists.txt` | Build PIC static `answer` and install its public header/archive |
| `include/cmake_math/answer.h`, `src/answer.cc` | Declaration and out-of-line implementation |
| `app/main.cc` | Native consumer, outside the library source directory |
| `:sources` | Explicit complete input filegroup for the CMake project |
| `//03-cmake-library:answer` | `cmake_forge` with exact installed exports |
| `//03-cmake-library:app` | Consumer with only `deps = [":answer"]` |

Source inputs and installed outputs are different contracts. The filegroup
declares what CMake reads; `install()` produces `include/cmake_math/answer.h` and
`lib/libanswer.a`; `exports` describes those paths at Bazel analysis time.

CMake compiles the archive with PIC, so the same file satisfies its static and
PIC-static forms. These are alternatives within one logical library, not two
unconditional links. The consumer declares no include/link path workaround.

## Build

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`. From the Forge repository root, enter it once:

```bash
cd examples
```

If already inside `examples/03-cmake-library`, use `cd ..` instead. Build the
CMake library and native consumer without executing the program:

```bash
../forge-bazel build --config=debug //03-cmake-library:app
../forge-bazel build --config=release //03-cmake-library:app
```

To build and export only the CMake library:

```bash
../forge-bazel build --config=debug //03-cmake-library:answer
../forge-bazel build --config=release //03-cmake-library:answer
```

Bazel invokes CMake, compiles the PIC archive, installs its header/library, and
exports the declared files. No separate `cmake` or `make` command is needed.
Success means exit zero and `Build completed successfully`. Building `:app`
produces `bazel-bin/03-cmake-library/app`; `:answer` alone exports only the library.
The output query below lists the install/export
files. Do not clean between configurations.

## Run

From the same `forge/examples` directory:

```bash
../forge-bazel run --config=debug //03-cmake-library:app
../forge-bazel run --config=release //03-cmake-library:app
```

Both commands must print `result=41` and exit zero. CMake produces a library,
not a dummy executable; `:app` is the actual runnable consumer.

## Inspect And Clean Up

```bash
../forge-bazel cquery --config=debug //03-cmake-library:answer --output=files
../forge-bazel aquery 'mnemonic("CppLink", //03-cmake-library:app)' --config=debug
```

Inspect the declared install/export outputs and the consumer link action. A
missing installed header or archive is a build error. The
[CMake guide](../../documents/cmake-forge.md) explains toolchain overlays,
additional inputs and cross-probe boundaries.
Inside `../forge-shell`, replace `../forge-bazel` with `bazel`.

Reuse the shared workspace and output base. No manual CMake directory, system
installation, or user Conan cache cleanup is part of this lesson.
