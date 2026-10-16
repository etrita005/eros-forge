# CMake Integration

`cmake_forge` builds a CMake project through `rules_foreign_cc` and publishes a
strict install interface. Load it from `@eros_forge//bazel:cmake_forge.bzl`.
Platform and mode selection are described in the [root guide](../README.md).

## Declared Sources

The `lib_source` filegroup must contain everything configuration, compilation,
generation, and installation read: CMakeLists, included `.cmake`, C/C++ sources,
headers, templates, patches, scripts, and configuration files.

```python
cmake_forge(
    name = "foo",
    lib_source = ":sources",
    out_static_libs = ["libfoo.a"],
    cache_entries = {"BUILD_TESTING": "OFF"},
)
```

This is an API fragment, not a complete project. The project must actually
install the declared library. Use `out_binaries` and `out_shared_libs` for other
installed products; `exports` defines the public interface when explicit control
is needed.

Pin downloaded source with a verified archive digest or fixed commit including
submodules. Keep module resolution locks in version control. Ordinary builds
must not clone a moving branch head.

Bazel globs stop at nested package boundaries. Expose vendored subpackages
explicitly. Do not remove project BUILD files to hide the boundary; any controlled
vendoring transformation must be limited to its intended directories.

## Install And Export

Use `cmake --install` with known `bin`, `lib`, and `include` destinations.
The adapter validates exact declared paths, file type/magic, executable
permissions, and shared-library SONAME naming. It does not search for the first
matching basename or create placeholder programs.

The optional `exports` descriptor is shared with the
[CMake/Conan adapter](cmake-conan-forge.md#analysis-time-interface). It defines
headers, include roots, public defines, logical library alternatives, link items,
programs, and runtime files. It is also usable without Conan.

For a versioned shared library, use its runtime SONAME path, such as
`lib/libfoo.so.1`, as `shared`. The install tree keeps the development alias and
real versioned file. Individual exported File copies may dereference install
symlinks; the complete tree remains the source of installation relationships.

`exports.runtime_files` declares dlopen-only plugins and resources as runtime
roots. `data` and explicit install mappings attach further runtime targets.
Use the [runtime-aware packaging path](deb-packaging.md) to validate the closure
and payload architecture. File-format validation alone is not an ELF-machine
architecture check.

CMake programs are ordinary file outputs, not a promise that the library target
is runnable with `bazel run`. Native consumers link through `deps`; test exports
provide explicit program entry points and layouts.

## Flags And Tools

Forge selects the generated toolchain, CMAKE_BUILD_TYPE, sanitizer configuration,
and debug requirements. Typed compiler arguments retain their argument boundaries.
The flags overlay is a target-configured `data` input; execution tools use
`build_data`. Target ABI flags must not be generated under an exec transition.

`--define=forge_jobs=N` controls the internal build budget. Bazel `--jobs=N`
controls outer action parallelism. Neither is a disk/inode retention policy.

Do not use undeclared `/usr/include`, `/usr/lib`, or system generators as a
dependency shortcut. Controlled installed tools require validated identities and
declared inputs; other dependencies need explicit targets.

## Cross Configuration

ARM64 cross presets use GCC 13 `aarch64-linux-gnu` tools. Their default compiler
headers/link libraries remain relevant inputs. `/opt/eros` supplies deployment
interpreter/RPATH conventions and a CMake search root; it is not automatically
the compiler's full sysroot. Follow the SDK validation requirements in the
[technical design](technical-design.md#toolchains).

`try_compile()` compiles and normally links but does not run the result.
`try_run()` requires maintained target values or a real executor. Do not fabricate
successful runtime results. `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY` only
changes a probe; it cannot replace actual executable linking or target execution.

## Symbols And Cache

With `separate_debug_info`, collect `eros_debug_info`, preserve its identity and
source records, and verify GDB source resolution. Release remains optimized.
Incomplete split DWARF is not an independently usable symbol set.

The Foreign-CC action environment/tool boundary must be reviewed in the actual
action graph. A toolchain feature or local incremental build is not proof of
independent-machine cache reuse. Use the environment and cache scenarios in
[the acceptance design](test-design.md); execution instructions are in
[tests/README](../tests/README.md).
