# EROS Forge

Forge uses Bazel 9 to build native C++, integrate CMake/Conan packages, and export
private Debian and test payloads in a controlled GCC 13 environment.

Start with the [documentation index](documents/README.md). The
[requirements](documents/requirements.md), [technical design](documents/technical-design.md),
and [acceptance design](documents/test-design.md) define the contracts and their
verification boundaries. Execution results belong in per-run reports.

## Environment And Setup

The currently built and locked local Docker environment is **Linux/amd64 only**.
`Dockerfile.amd64` is for native Linux x86_64 build hosts; `Dockerfile.arm64`
is an unverified recipe for native Linux ARM64 build hosts (including an ARM64
Linux VM in OrbStack). On a Linux x86_64 host, install Python 3 and Docker,
ensure the Docker daemon is accessible, and check out the Forge source. The
host does not need Bazel, GCC, CMake, Conan or a target SDK. From the Forge
root, build the local amd64 image if it is not already present:

```bash
docker build --platform linux/amd64 -f Dockerfile.amd64 -t eros-forge-builder:local .
```

If downloads require the host's `127.0.0.1:7890` proxy, use host networking
for the build and supply proxy build arguments as needed instead:

```bash
docker build --platform linux/amd64 -f Dockerfile.amd64 --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7890 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7890 \
  --build-arg http_proxy=http://127.0.0.1:7890 \
  --build-arg https_proxy=http://127.0.0.1:7890 \
  -t eros-forge-builder:local .
```

These build arguments affect commands inside the Dockerfile. Pulling the base
image is done by the Docker daemon, which needs its own proxy configuration
if Docker Hub is inaccessible; neither configuration is baked into the image.

The amd64 Dockerfile uses the Tsinghua Ubuntu APT mirror and verifies the downloaded
Bazel binary against its fixed SHA256. Availability of that upstream download
and the APT/Python package sources is still required for a rebuild; this image
is not a reproducibly published registry artifact. The reviewed local image is
`sha256:81230a0b49d2e588491e1652164ad4c4aba853605366c306e73492a2883b1e30`.
Check the newly built ID and `linux/amd64` architecture:

```bash
docker image inspect eros-forge-builder:local --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

`docker/image.lock.json` pins the **local Docker image ID**, environment digest
and missing SDK identity; the `eros-forge-builder:local` tag alone does not
authorize an upgrade. A different image ID makes both launchers fail closed.
For an intentional rebuild, inspect and review the new image ID and captured
environment/SDK identities, update the lock together, then rerun local checks.
The capture and upgrade procedure is in the
[technical design](documents/technical-design.md#local-image-baseline).

On a native Linux ARM64 build host, the separate candidate recipe can be built:

```bash
docker build --platform linux/arm64 -f Dockerfile.arm64 \
  -t eros-forge-builder:arm64-candidate .
```

It uses the Ubuntu `ubuntu-ports` mirror and its own hashed Python dependency lock.
**No ARM64 image has been built or validated here.** The current image lock
and host launchers accept amd64 only; an ARM64 build would first need toolchain
and Forge tests on that host, followed by its own reviewed lock and launcher
platform support. On OrbStack, verify proxy reachability from the Linux VM:
`127.0.0.1` in the VM is not assumed to be macOS's loopback address.

Use the executable entry points from the Forge root:

```bash
./forge-bazel --bazelrc=bazel/bazelrc build //bazel/toolchain:validate_environment
./forge-bazel --bazelrc=bazel/bazelrc run --config=debug //tests/fixtures/basic:native
./forge-shell
# Inside the shell, in the Forge root:
bazel --bazelrc=bazel/bazelrc info output_base
```

`forge-bazel` passes Bazel arguments through, while `forge-shell` enters the
same persistent workspace container; both use the caller's working directory.
In the shell use `bazel` directly. From `examples/`, use `../forge-bazel` on
the host or `bazel` in the shell: its `.bazelrc` already imports Forge's rc.
The persistent container runs as the caller's UID/GID and uses host networking,
including access to a host loopback proxy when configured. The launchers check
the locked image and tool/SDK identity before use; they do not pull or publish
an image, nor fall back to bare-metal building. See
[the examples](examples/README.md) for eight verified Debug/Release native runs;
these do not replace target execution or cross-machine acceptance.

The local entry permits one active container instance per source workspace:
another `FORGE_INSTANCE` for the same checkout fails rather than overwrite
`bazel-bin` links. Use separate checkouts for parallel work. Different instance
state and the target SDK/CPU runtime are not interchangeable.

The generated environment manifest identifies the actual tool files and
support libraries; validation checks their content and version policy. The
ARM64 native preset remains a design target, not a locally supplied ARM64
image. The current x86_64 container has cross tools, but lacks a matching
target SDK and target execution environment; cross builds/ELF checks cannot
establish target ABI or deployment acceptance.

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

From the Forge repository root, select the rc explicitly. In the container
shell use `bazel` instead of `./forge-bazel`:

```bash
python3 bazel/toolchain/generate_files.py --check
./forge-bazel --bazelrc=bazel/bazelrc build //bazel/toolchain:validate_environment
./forge-bazel --bazelrc=bazel/bazelrc run --config=debug //tests/fixtures/basic:native
```

The fixture command checks the installed build environment. Start learning with
the [beginner examples](examples/README.md): lessons 01-04 cover native programs,
libraries, CMake and a locked Conan dependency; lessons 05-08 cover private
runtime delivery, Debian packaging, Release symbols and sanitizer controls in
the same workspace. The [example roadmap](documents/examples-plan.md) identifies
the remaining Batch C.

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

## Export The Cross Runtime

Inside the controlled Linux build container, explicitly export the installed
AArch64 GCC 13 runtime without installing anything or changing ordinary builds:

```bash
bash bazel/toolchain/export_runtime.sh \
  --output /tmp/kilo/eros-runtime-arm64.tar.gz
```

The default compiler is `aarch64-linux-gnu-gcc-13`; `--compiler /path/to/gcc`
selects another installed driver with the same GCC-major and target contract.
The tool requires Bash 4+, GNU coreutils/tar/gzip, and `aarch64-linux-gnu-readelf`.
It does not require Python. The output directory must exist, and existing output
files or symlinks are never replaced.

The archive contains `opt/eros/lib/` with libc, libm, libstdc++, libgcc_s and the
AArch64 loader, available compatibility/atomic/resolver/sanitizer runtimes, and
their transitive `DT_NEEDED` libraries. Discovery uses the selected compiler's
`-print-file-name` only, with no host-library fallback or target execution.
Missing core libraries or dependencies, wrong ELF architecture/SONAMEs, and
filename collisions fail before publishing the archive. SONAME and query aliases
are rebased to relative links to their real payloads inside `lib/`.

`opt/eros/TOOLCHAIN` records compiler/binutils identities, runtime source paths,
hashes, relative links and unavailable optional queries. `opt/eros/SHA256SUMS`
checks the toolchain record and all library names. Archive order, ownership,
timestamps and gzip headers are normalized for identical inputs. Review in a
new staging directory, not in the build container's `/opt/eros`:

```bash
review_dir=$(mktemp -d /tmp/kilo/eros-runtime-review.XXXXXX)
tar -xzf /tmp/kilo/eros-runtime-arm64.tar.gz --directory="$review_dir"
(cd "$review_dir/opt/eros" && sha256sum --check SHA256SUMS)
```

This is a foundation runtime payload, not a complete SDK/sysroot: it does not
include target headers, development archives, locales, gconv/NSS modules loaded
dynamically, or deployment configuration. It does not rewrite library RUNPATHs
or configure the target loader's search paths. SDK maintainers must verify
target ABI, indirect library resolution and device execution separately; merely
extracting this archive does not establish D02 or production readiness. Application
private libraries remain the responsibility of the normal tar/deb packaging rules.

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
| Cross-toolchain foundation runtime archive | `bash bazel/toolchain/export_runtime.sh` | [Runtime export](#export-the-cross-runtime) |
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
