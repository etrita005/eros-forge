# 07: Debug Optimized Release Code

Goal: keep Release optimization while publishing independent DWARF symbols and
matching identity metadata. A debugger must resolve a real source location from
the separately shipped symbols, not from an unstripped build-tree binary.

## Files And Targets

| File/target | Role |
| --- | --- |
| `main.cc` | Optimized function with a stable source line |
| `//07-release-symbols:app` | Release program; published binary is stripped |
| `//07-release-symbols:symbols` | `eros_debug_info` export for the matching `.debug` file |

`pkg_eros_tar(..., output_group = "eros_debug_info")` collects the declared
symbol outputs and an identity manifest. The target does not embed the symbols
back into the published runtime binary. The manifest records the build ID,
binary/debug hashes and the `requires_matching_payload` contract.

## Build

Working directory for every command below: `forge/examples`.

```bash
../forge-bazel build --config=release //07-release-symbols:app
../forge-bazel build --config=release //07-release-symbols:symbols
```

The first command produces the stripped runtime program. The second produces
`bazel-bin/07-release-symbols/symbols.tar.gz`; it must be used with the matching
release binary. Do not substitute a Debug build or symbols from another build ID.

## Inspect The Split

```bash
readelf -S bazel-bin/07-release-symbols/app | grep -E 'debug|gnu_debuglink'
root=$(mktemp -d /tmp/kilo/forge-release-symbols.XXXXXX)
tar -xzf bazel-bin/07-release-symbols/symbols.tar.gz --directory="$root"
find "$root/opt/eros/forge-example-release-symbols" -name '*.debug' -print
readelf -n bazel-bin/07-release-symbols/app
```

The published binary should contain `.gnu_debuglink` but no `.debug_info`; the
separate file should contain DWARF. The build ID in the binary, the `.debug`
file and `debug_manifest.json` must agree.

## Resolve A Source Breakpoint

Use GDB with the extracted symbol directory and the matching stripped binary:

```bash
symbol_dir=$(dirname "$(find "$root/opt/eros/forge-example-release-symbols" \
  -type f -name '*.debug' ! -path '*/.build-id/*' -print -quit)")
gdb -nx -batch \
  -ex "set debuginfod enabled off" \
  -ex "set debug-file-directory $symbol_dir" \
  -ex "file bazel-bin/07-release-symbols/app" \
  -ex "break forge_release_symbol" \
  -ex "info line forge_release_symbol"
```

GDB must report a resolved breakpoint and a line in
`07-release-symbols/main.cc`. Running the program must still print `result=41`.
The command above does not execute the program, so it does not require target
core collection or a target deployment environment.

## Verify

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 07-release-symbols/check.py
```

The checker validates the Release run, manifest hash/build-ID agreement, stripped
binary and separate DWARF, then uses GDB to resolve an actual source breakpoint.
This is local symbol evidence; matching target cores and CI symbol storage remain
separate acceptance scopes. Inside `../forge-shell`, replace `../forge-bazel`
with `bazel`.
