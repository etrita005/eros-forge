# Locked CMake And Conan Integration

`cmake_conan_forge` runs dependency preparation followed by a CMake install/export
action. Load it from `@eros_forge//bazel:cmake_conan_forge.bzl`.

## Build Inputs

| Input | Contract |
| --- | --- |
| `conanfile` | The package's Conan requirements/recipe |
| `lockfile` | Mandatory, complete locked dependency input |
| `cmake_lists`, `srcs` | The CMake project and declared source files |
| `extra_srcs` | Included CMake, templates, scripts, patches, and recipe support files |
| `exports` | Analysis-time public/install interface |
| `file_remote` / `local_recipes` | Declared source-only recipe indexes |
| `remote_config` | Declared remote configuration and binary identity metadata |
| `cache_archive` | Declared Conan cache archive input |
| `jobs` | Internal default budget, overridden by `--define=forge_jobs=N` |

The macro selects host/build profiles and toolchain from Forge configuration.
Output parameters include `out_binary`, `out_static_libs`, `out_shared_libs`,
`hdrs`, and `includes`; use an explicit descriptor for a complete public contract.

Normal builds use strict `--lockfile` and `--build=missing`. Missing variants
build from locked source. Builds do not update locks, write back project sources,
or use the user's `~/.conan2` as mutable working state.

## Lock Maintenance

The updater runs outside ordinary build actions, in an isolated Conan home. It
does not inherit the user's remotes. Supply a source explicitly:

```bash
bazel --bazelrc=bazel/bazelrc run //bazel/tools:conan_lock_update -- path/to/package --file-remote path/to/recipe-index
```

For a Conan service, use `--remote NAME=URL` instead of or alongside file indexes.
Both options are repeatable. Optional `--host-profile`, `--build-profile`, and
`--lockfile` select the maintenance inputs/output. Paths are resolved from the
calling workspace. Consumers can invoke `@eros_forge//bazel/tools:conan_lock_update`.

Review and commit the resulting package lock and affected export declarations.
A lock update is an intentional dependency change, not a side effect of building.

## Profiles And Package Identity

Conan `host` describes target libraries; `build` describes the execution machine.
ARM64 target libraries use `arch=armv8` and the AArch64 toolchain. Build tools use
their host-native profile without inheriting target sanitizers.

The package identity covers the controlled environment, compiler/C++ ABI,
configuration, required flags, PIC/linkage settings, and symbol requirements.
Forge explicitly includes required conf dimensions and rejects recipes that
erase them. Same name/version alone does not establish binary compatibility.

Profiles request `-g`, static preference, and PIC where applicable. Missing
sanitizer or usable-symbol variants must build from source or fail; ordinary
Release binaries are not an acceptable substitute. Tool/sysroot selection and
SDK ABI verification follow [the technical design](technical-design.md).

## Complete Snapshot

The action uses private `HOME`/`CONAN_HOME` and declared Python/tool inputs.
It emits actual package headers, libraries, runtime files, controlled relative
links, relocatable metadata, and manifests containing revisions, package IDs,
variant information, and content hashes.

Host and build contexts remain distinct. Build tools may exist in the snapshot
but are not copied into the target runtime payload. Private Conan state is
removed before downstream CMake use. The snapshot must also work after being
moved to another absolute path.

Source records preserve patched sources and relevant generated headers, not
producer CMake caches, compiler objects, or environment scripts. Precompiled
inputs without available sources explicitly record that limitation.

## Analysis-Time Interface

`exports` uses exact install-relative paths. The reference shape is:

```python
exports = {
    "headers": ["include/foo.h", "include/generated.h"],
    "includes": ["include"],
    "defines": ["FOO_PUBLIC=1"],
    "libraries": [
        {"name": "foo", "static": "lib/libfoo.a",
         "pic_static": "lib/libfoo.a", "shared": "lib/libfoo.so.1"},
        {"name": "bar", "pic_static": "conan/bar/lib/libbar.a"},
    ],
    "linkopts": ["-pthread"],
    "binaries": ["bin/app"],
    "runtime_files": ["lib/plugin.so", "share/app/config.json"],
}
```

These paths must correspond to actual installed products. A single logical
library contains alternative static/PIC/shared forms; they are not linked
unconditionally together. Include required transitive static libraries.
Versioned shared declarations name the runtime SONAME path.

The descriptor constructs `CcInfo` during analysis. Consumers use `deps = [":foo"]`
without duplicating includes/linkopts or knowing Conan cache paths. Execution
generates and validates those declared files, not arbitrary extra targets.

`cmake_build` is not an executable rule. Missing declarations fail; pure libraries
need no placeholder executable. The action validates paths, file magic/type,
permissions and SONAME names. It does not unconditionally validate ELF machine
architecture; runtime/DEB exports perform their corresponding architecture checks.

Snapshot/install trees preserve relative SONAME chains. Individual `.exports`
File copies can dereference symlinks. Use the complete install metadata for
runtime packaging rather than flattening public link artifacts manually.

## Runtime And Symbols

`ErosInstallInfo` carries installation metadata. `exports.runtime_files` marks
same-target plugins/resources as explicit runtime roots; `data` attaches further
runtime targets. The [packaging guide](deb-packaging.md) defines closure checking.

`ErosDebugInfo` and `eros_debug_info` expose matching symbols and manifests,
including transitive Conan packages. Target and build-context binaries use
matching binutils. Full DWARF and source records are needed for independent
archives; an incomplete split-DWARF skeleton is rejected.

## Cache And Sources

Custom actions use `no-remote-exec`, allowing eligible results to be cached while
misses execute locally. Recipe locks alone do not pin mutable binary revisions.
Declared remote/cache inputs and actual selected binary identities must satisfy
the acquisition checks; the snapshot is the downstream input boundary.

A `file://` recipe index is source-only and does not provide a precompiled binary
store or arbitrary recipe revisions. Binary/revision acceptance uses a controlled
Conan service. Local reuse is not proof of cross-machine hits.

All source/support inputs must be explicit. Cross `try_run` needs a real executor
or maintained target results; compilation and interpreter paths do not prove
runtime ABI compatibility. See [test scopes](test-design.md) and
[runner operations](../tests/README.md).
