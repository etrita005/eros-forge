# Runtime And Debian Packages

Load `pkg_eros_tar`, `pkg_eros_deb`, `pkg_eros_deb_multiarch`, and
`eros_test_package` from `@eros_forge//bazel:deb.bzl`. Native wrappers and install
maps are in `@eros_forge//bazel:runtime.bzl`.

## Runtime-Aware Payloads

The packaging API composes a runtime export with Debian metadata:

```python
pkg_eros_tar(
    name = "payload",
    srcs = [":app"],
    package = "my-package",
)

pkg_eros_deb(
    name = "deb",
    package_name = "my-package",
    data = ":payload",
    description = "Private application and runtime closure",
    maintainer = "Team <team@example.invalid>",
)
```

This API fragment assumes a declared `:app` target with a usable runtime
interface. `eros_cc_binary` and `eros_cc_library` preserve native C++ dependency
semantics and provide installation metadata, relative RUNPATH and debug exports.
`eros_install_map(files={label: relative_destination})` assigns explicit paths.

`pkg_eros_tar` accepts `srcs`, optional `output_group`, and an output name.
`package` sets payload identity and its default private root; `package_dir`
can override the tar prefix. Keep that identity consistent with the deb name.
`pkg_eros_deb` takes a single tar-producing `data` target;
`package` and `package_name` name the Debian package and cannot conflict.

## Providers And Closure

`ErosInstallInfo` maps declared files/directories to private relative destinations
and carries provenance. `ErosDebugInfo` carries symbols and identity manifests.
The runtime aspect follows `deps` and `data`, combining these with native runfiles.

Runtime-aware exports retain programs, explicitly declared plugins/resources,
and actual selected shared dependencies. They prune unused shared alternatives
when static linking is selected. ELF `DT_NEEDED` checks cannot discover dlopen
plugins, so declare those through `data`/install maps or CMake `runtime_files`.

```text
/opt/eros/<package>/bin/      programs
/opt/eros/<package>/lib/      private libraries and plugins
/opt/eros/<package>/share/    resources
/opt/eros/lib/               controlled deployment runtime
```

Each shared-library layer needs an appropriate `$ORIGIN` RUNPATH; a program's
RUNPATH does not automatically resolve all indirect dependencies. Deployment
must work without the build machine's `LD_LIBRARY_PATH`.

`pkg_eros_tar` and `eros_test_package` validate their runtime-aware closure:
missing private libraries, conflicting destinations, dangling/escaping links,
and unsafe paths fail. Identical-content files with compatible normalized modes
are deduplicated, including public export copies; SONAME links are preserved.

Keep `libfoo.so -> libfoo.so.1 -> libfoo.so.1.2` and the real file. SDK runtime
boundaries come from the controlled environment, not an ad hoc scan of installed
host libraries. A missing SDK runtime identity is not target deployment proof.

`pkg_eros_deb` also accepts an arbitrary tar. That wrapping path validates archive
safety and ELF/architecture agreement, **not a complete dependency closure**.
Use a runtime-aware exporter when Forge must establish runtime completeness.

Different packages may carry private versions without file ownership conflicts.
This does not guarantee same-process symbol, global-state, or C++ ABI isolation.

## Architecture And Version

| Target CPU | Debian architecture |
| --- | --- |
| x86_64 | `amd64` |
| ARM64 | `arm64` |
| Unknown | Analysis error |

`architecture="all"` is explicit and must not contain target ELF. Explicit
metadata inconsistent with payload ELF fails. Changing an architecture string
cannot turn one machine-code payload into another architecture.

Nonempty version inputs have this precedence:

1. `version` attribute.
2. Declared action environment `DEB_VERSION`.
3. `--define=DEB_VERSION`.
4. `0.1.0`.

The shared rc declares `--action_env=DEB_VERSION`. Changing its value affects the
version action key without `bazel clean`. Control fields and maintainer scripts
must be explicit; see [deb.bzl](../bazel/deb.bzl) for supported attributes.

## Multiarch And Configurations

`pkg_eros_deb_multiarch` configures the payload dependency through a split
transition. Each branch sets the actual platform and Forge preset, builds its
own payload and emits a preset-qualified output with its own provenance.

`architectures=["amd64", "arm64"]` selects native x86_64 and cross ARM64 on a
compatible x86_64 execution host. Explicit `presets` select supported variants,
including `linux_arm64` and `linux_arm64_cross_arm64` on an ARM64 host.

Two ARM64 variants have the same Debian architecture but different target
configuration/interpreter conventions. They do not prove a dual-CPU build.
Unavailable host tools or incomplete branch inputs fail the aggregate. A
`manual` tag only affects wildcard selection, not transition semantics or an
explicit dependency's execution.

## Debug And Test Archives

Debug processing retains original link products as build inputs, extracts
symbols with matching target tools, and strips debug sections only from published
copies where appropriate. Collect `eros_debug_info` and retain build IDs, hashes,
source inventories, and variant identity. Missing or substituted symbols fail
validation; a feature name or split-DWARF filename is insufficient.

Symbol-only archives require their matching payload for validation. Test packages
combine the runtime layout with symbols, entry points and environment/SDK
metadata. The debug archive uses distinct directories for transitive native,
CMake and Conan symbols and records relocatable source inventories.

`eros_test_package(srcs=..., entry_points=...)` never executes the program.
CI extracts it in the matching target runtime, runs the declared entry points,
captures results/core files and associates the matching symbols.

Implementation modules are [runtime.bzl](../bazel/runtime.bzl),
[deb.bzl](../bazel/deb.bzl), and [the packaging driver](../bazel/packaging/driver.py).
Behavioral criteria are in [the acceptance design](test-design.md); commands and
evidence handling are in [tests/README](../tests/README.md).
