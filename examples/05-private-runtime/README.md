# 05: Ship A Private Runtime

Goal: build a program against a shared library, declare a resource, and run the
result from a private `/opt/eros/<package>` layout without `LD_LIBRARY_PATH`.
Prerequisites are the native environment in the [workspace guide](../README.md);
lesson 02 need not have been built.

## Files And Targets

| File/target | Role |
| --- | --- |
| `include/private_math/answer.h` | Public declaration of the shared-library function |
| `src/answer.cc` | Out-of-line implementation in a shared library |
| `app/main.cc` | Consumer that calls the library and reads the installed resource |
| `resource.txt` | Resource content copied into the private payload |
| `//05-private-runtime:app` | Runnable native program |
| `//05-private-runtime:runtime_tar` | Checked tar with the full private runtime |

`eros_cc_library` uses `linkstatic = False` to produce a real shared object.
The versioned install names create the `libforge_private_answer.so ->
libforge_private_answer.so.1 -> libforge_private_answer.so.1.0.0` chain.
`eros_install_map` maps the resource to `share/private-runtime.txt`, and
`data = [":resource"]` keeps it in the dependency closure. `pkg_eros_tar`
collects the program, selected shared library, resource and provenance under
`/opt/eros/forge-example-private-runtime`.

## Build

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`.

```bash
../forge-bazel build --config=debug //05-private-runtime:runtime_tar
../forge-bazel build --config=release //05-private-runtime:runtime_tar
```

Each build must exit zero with `Build completed successfully`. The payload is
`bazel-bin/05-private-runtime/runtime_tar.tar.gz`; building `:runtime_tar` also
builds `:app` and its library. Do not clean between configurations.

## Run The Bazel Target

```bash
../forge-bazel run --config=debug //05-private-runtime:app
```

Bazel runs the generated private runtime layout, so this must print
`result=41 marker=FORGE_PRIVATE_RUNTIME_MARKER layout=private`.

## Run The Extracted Payload

Extract to a temporary directory and run the installed program with no library
path override:

```bash
root=$(mktemp -d /tmp/kilo/forge-private-runtime.XXXXXX)
tar -xzf bazel-bin/05-private-runtime/runtime_tar.tar.gz --directory="$root"
env -u LD_LIBRARY_PATH -u LD_PRELOAD \
  "$root/opt/eros/forge-example-private-runtime/bin/app"
```

The command must print
`result=41 marker=FORGE_PRIVATE_RUNTIME_MARKER layout=private` and exit zero.
Inspect the loaded files and RUNPATH:

```bash
readelf -d "$root/opt/eros/forge-example-private-runtime/bin/app" | \
  grep -E 'NEEDED|RUNPATH'
find "$root/opt/eros/forge-example-private-runtime" -type l -printf '%p -> %l\n'
```

The program needs `libforge_private_answer.so.1` and resolves it through
`$ORIGIN/../lib`. The public link and versioned SONAME links must remain intact;
do not replace them with one flat copy.

## Verify

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 05-private-runtime/check.py
```

The checker builds Debug and Release payloads in the shared output base, extracts
each one, checks the library chain and resource, and runs the program with
`LD_LIBRARY_PATH` removed. It also checks the normal `bazel run` path. This is
native extraction and local execution evidence, not a clean target installation
or target ABI check.

Inside `../forge-shell`, replace `../forge-bazel` with `bazel`. Reuse this
workspace/output base and follow the [workspace cleanup](../README.md#resources-and-cleanup)
only after saving diagnostics.
