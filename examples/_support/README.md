# Shared Example Inputs

`conan-index` is a source-only Conan local recipe index. Its `recipes` directory
contains `tiny_math/1.0`, a real compiled library used by the locked-dependency
lesson. It is not a Conan server or binary store.

The public `:recipe_index` filegroup declares every index/recipe input. Consumers
keep their own locks. The recipe verifies the source SHA256 in `conandata.yml`;
the lock pins the recipe revision, which also covers exported support files.

The lesson source is distributed under the repository's MIT license; the recipe
also installs the supplied license into its package. Update source digests and
consumer locks explicitly when changing this dependency.

## Build The Dependency

This directory is shared input infrastructure, not a standalone runnable lesson.
Build through the locked consumer so Forge applies the intended profile, lock
and private Conan home. From `forge/examples`:

```bash
bazel build --config=debug //04-conan-locked:answer
bazel build --config=release //04-conan-locked:answer
```

If starting in `examples/_support`, enter the shared workspace with `cd ..`
first. The `:recipe_index` filegroup alone only declares source inputs; it does
not compile `tiny_math`. No manual Conan export/install is required. See
[lesson 04](../04-conan-locked/README.md) for program build/run and snapshot
inspection commands.
