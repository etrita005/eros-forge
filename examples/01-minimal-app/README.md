# 01: Build And Run A Native Program

Goal: use a public Forge rule to build a real executable and run it natively.
Use the local Linux/amd64 container described in the
[workspace guide](../README.md). No target SDK, remote cache or Conan server
is needed.

## Files And Target

| File/target | Role |
| --- | --- |
| `main.cc` | Compute 20 * 2 + 1 and check the result |
| `BUILD.bazel` | Declare `eros_cc_binary(name = "app")` |
| `//01-minimal-app:app` | Runnable native target |

The shared module and rc select Forge and the supported native toolchain.
There is no tutorial-only build macro between the BUILD file and Forge.

## Build

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`. From the Forge repository root, enter it once:

```bash
cd examples
```

If already inside `examples/01-minimal-app`, use `cd ..` instead. Build the
program without executing it:

```bash
../forge-bazel build --config=debug //01-minimal-app:app
../forge-bazel build --config=release //01-minimal-app:app
```

Success means Bazel exits zero and reports `Build completed successfully`.
The executable is available as `bazel-bin/01-minimal-app/app` relative to the
shared workspace. `bazel-bin` refers to the selected build configuration; do not
clean between Debug and Release.

## Run

From the same `forge/examples` directory:

```bash
../forge-bazel run --config=debug //01-minimal-app:app
../forge-bazel run --config=release //01-minimal-app:app
```

Both commands must print `result=41` and exit zero. Debug and Release select
different build modes; neither implicitly enables a sanitizer.

## Inspect And Clean Up

```bash
../forge-bazel cquery --config=debug //01-minimal-app:app --output=files
```

The Forge rules forward a real executable and runtime layout. The query lists
declared files; `bazel run` chooses the executable, not a guessed basename.
These host commands also work with `bazel` instead of `../forge-bazel` inside
`../forge-shell`.

No source files or system installation are modified. Reuse this workspace for
the next lesson. Do not clean between mode switches. When all lessons are
finished, follow the workspace's cache cleanup instructions.
