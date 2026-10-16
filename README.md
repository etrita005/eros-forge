# EROS Forge

Forge uses Bazel 9 to build native C++, integrate CMake/Conan packages, and export
private Debian and test payloads in a controlled GCC 13 environment.

Start with the [documentation index](documents/README.md). The
[requirements](documents/requirements.md), [technical design](documents/technical-design.md),
and [acceptance design](documents/test-design.md) define the contracts and their
verification boundaries. Execution results belong in per-run reports.

## Environment And Setup

Use a supported Linux x86_64 or ARM64 environment with the prescribed GCC,
binutils, CMake, Make, Python and Conan installation. The generated environment
manifest identifies their actual files and support libraries; environment
validation checks content and version policy.

The module is `eros_forge` version `0.1.0`. Dependencies are `rules_cc 0.2.14`,
`rules_pkg 1.0.1`, `platforms 1.0.0`, and `rules_foreign_cc 0.15.1`.
Keep `MODULE.bazel.lock` and package Conan locks in version control.

A local consuming module can declare:

```python
bazel_dep(name = "eros_forge", version = "0.1.0")
local_path_override(module_name = "eros_forge", path = "../forge")
```

Import the shared rc from the consuming workspace's `.bazelrc`, adjusting the
relative path to the checkout layout:

```text
import %workspace%/../forge/bazel/bazelrc
```

From the Forge repository root, select the rc explicitly:

```bash
python3 bazel/toolchain/generate_files.py --check
bazel --bazelrc=bazel/bazelrc build //bazel/toolchain:validate_environment
bazel --bazelrc=bazel/bazelrc run --config=debug //tests/fixtures/basic:native
```

The fixture command checks the installed build environment; the teaching
projects described in the [beginner example plan](documents/examples-plan.md)
are planning material, not implemented example directories.

## Platforms And ABI

| Preset | Execution CPU | Target CPU |
| --- | --- | --- |
| `linux_x86_64` | x86_64 | x86_64 |
| `linux_arm64` | ARM64 | ARM64 |
| `linux_x86_64_cross_arm64` | x86_64 | ARM64 |
| `linux_arm64_cross_arm64` | ARM64 | ARM64 |

No platform config, or `--config=auto`, selects supported native execution.
Explicit presets validate the execution host and target platform; installing a
compiler does not waive those restrictions.

ARM64 cross targets use system `aarch64-linux-gnu` GCC 13 and matching binutils.
Compiler-default headers/sysroot/link directories remain active. `/opt/eros`
provides deployment interpreter/RPATH conventions and a CMake search root; it
is **not automatically selected as a full compiler sysroot**.

The cross interpreter is `/opt/eros/lib/ld-linux-aarch64.so.1`. If the deployment
SDK is absent, build/ELF checks can proceed with runtime identity marked
unverified. A loader path does not prove glibc ABI agreement. Production needs
matching target headers, libraries, loader and runtime, plus target execution
evidence. See [toolchain design](documents/technical-design.md#toolchains).

## Modes And Sanitizers

`--config=debug` selects Debug without implicit sanitizers. `--config=release`
selects optimized Release with `-g` and `separate_debug_info`.
`--features=-separate_debug_info` disables independent-symbol delivery.

Supported sanitizer configs are `asan`, `ubsan`, `tsan`, and `asan_ubsan`.
Both ASan/UBSan request orders normalize to the supported compound configuration.
`no_sanitizer` clears effective state. MSan, ASan+TSan, TSan+UBSan and unsupported
combinations are rejected. Use these configs rather than injecting raw
sanitizer flags into individual build paths.

## Public Interfaces

| Need | Entry point | Guide |
| --- | --- | --- |
| Native C++ with runtime/symbol metadata | `eros_cc_binary`, `eros_cc_library` | [Packaging](documents/deb-packaging.md) |
| CMake build | `cmake_forge` | [CMake](documents/cmake-forge.md) |
| Locked Conan plus CMake | `cmake_conan_forge` | [CMake/Conan](documents/cmake-conan-forge.md) |
| Private runtime tar/deb | `pkg_eros_tar`, `pkg_eros_deb` | [Packaging](documents/deb-packaging.md) |
| Real split configurations | `pkg_eros_deb_multiarch` | [Packaging](documents/deb-packaging.md#multiarch-and-configurations) |
| CI test closure | `eros_test_package` | [Packaging](documents/deb-packaging.md#debug-and-test-archives) |

CMake public interfaces are declared with `exports`: headers, includes, defines,
logical static/PIC/shared alternatives, transitive links, binaries and runtime
roots. Consumers need only `deps`. Exact installed outputs must exist; library
targets do not need executable placeholders.

Conan builds require a complete lockfile, isolate their home, materialize actual
dependencies, and remove producer state before downstream use. Dependency
updates are explicit operations with explicit sources, described in the Conan
guide. Ordinary builds do not update locks or use mutable user caches.

Runtime-aware export collects programs, selected dynamic dependencies, declared
plugins and resources into `/opt/eros/<package>/{bin,lib,share}`. Every dynamic
layer needs its own appropriate relative RUNPATH. Wrapping an arbitrary tar as
a deb validates archive safety and architecture, not the entire runtime closure.

## Symbols, Cache And Verification

Collect the `eros_debug_info` output group for matching independent symbols and
source identities. Preserve build IDs/hashes and source mappings with the
published payload. A `.debug` section or compiler flag alone does not prove
usable third-party source debugging.

Custom actions restrict remote execution with `no-remote-exec`; cache misses
execute locally. Complete declared inputs/outputs and pinned acquisition
identities are prerequisites for reuse. Independent-machine cache hits need
their own evidence, not just a fast local rebuild.

[tests/README](tests/README.md) documents TC filtering, prerequisites, reports,
resource management and PASS/FAIL/SKIP/BLOCKED. Build, local extraction, matching
target execution and remote-cache verification are distinct acceptance scopes.
