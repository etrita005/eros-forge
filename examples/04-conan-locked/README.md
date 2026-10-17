# 04: Consume A Locked Conan Dependency

Goal: build a CMake library with a real compiled Conan dependency, then expose
one complete dependency to a plain Bazel consumer. Use the native environment
in the [workspace guide](../README.md). No Conan server, public binary remote,
user-cache setup or earlier lesson build is needed.

## Files And Targets

| File/target | Role |
| --- | --- |
| `conanfile.txt`, `conan.lock` | Package-local requirement and reviewed recipe revision |
| `CMakeLists.txt` | Find `tiny_math`, build the bridge, install its public interface |
| `include/conan_math/answer.h`, `src/answer.cc` | Public API and actual call into the dependency |
| `app/main.cc` | Native consumer with only `deps = [":answer"]` |
| `//_support:recipe_index` | Declared local source-only Conan index |
| `//04-conan-locked:answer` | CMake/Conan export, including required transitive static archive |
| `//04-conan-locked:app` | Runnable consumer |

The bridge calls `tiny_math::transform` from its compiled archive. The
dependency is not header-only. The public `exports` descriptor includes both
`libanswer.a` and the dependency's PIC archive because static linking still
needs that private implementation. The consumer does not name either file.

## Build

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`. From the Forge repository root, enter it once:

```bash
cd examples
```

If already inside `examples/04-conan-locked`, use `cd ..` instead. Build the
consumer, CMake library and locked Conan dependency without running the program:

```bash
bazel build --config=debug //04-conan-locked:app
bazel build --config=release //04-conan-locked:app
```

To build only the exported library and its locked dependency:

```bash
bazel build --config=debug //04-conan-locked:answer
bazel build --config=release //04-conan-locked:answer
```

The supplied `conan.lock` and local recipe index are sufficient for a normal
build. Do not run `conan install`, export packages to the user cache, start a
server, or regenerate the lock first. On a cache miss Forge builds the dependency
from the locked source before configuring and installing the CMake library.

Each command must exit zero with `Build completed successfully`. Building `:app`
produces `bazel-bin/04-conan-locked/app`; `:answer` alone does not build the consumer.
The snapshot query below lists the declared
dependency outputs. Reuse the same output base when switching configurations.

## Run

From the same `forge/examples` directory:

```bash
bazel run --config=debug //04-conan-locked:app
bazel run --config=release //04-conan-locked:app
```

Both commands must print `result=41` and exit zero. The index supplies source,
not precompiled packages, so Conan builds the locked dependency with the selected
profile. Its source digest is checked against the declared `conandata.yml`.
Normal builds do not change the lock or user Conan cache.

## Inspect The Snapshot

```bash
bazel cquery --config=debug //04-conan-locked:answer_conan --output=files
```

The snapshot and manifest are declared outputs containing actual files, locked
revisions, package identity and hashes. The manifest records that the private
producer home was removed. Headers/libraries do not point into `~/.conan2`.
The [Conan guide](../../documents/cmake-conan-forge.md) describes these contracts.

## Explicit Maintenance

Do not update locks as part of the first build. When intentionally changing the
supplied recipe or requirement, review the source digest and then run:

```bash
bazel run --config=release @eros_forge//bazel/tools:conan_lock_update -- 04-conan-locked --file-remote _support/conan-index
```

Review the lock and export changes and include them with the source update.
The helper uses an isolated home and the explicit index, not user remotes.
The index root contains `recipes/`; passing the `recipes/` directory itself is
not the same path.

Reuse the shared Bazel output base. Cleanup applies to its owned build state,
not to source recipes, reviewed locks or the user's Conan cache.
