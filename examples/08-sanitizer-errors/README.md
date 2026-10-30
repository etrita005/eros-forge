# 08: Detect Instrumented Faults

Goal: build the same program with Forge sanitizer configurations and observe
faults in both business code and a compiled dependency. The default invocation
is error-free; runtime arguments select the fault without source edits.

## Files And Targets

| File/target | Role |
| --- | --- |
| `main.cc` | Business functions and command-line fault selection |
| `dependency.cc`, `dependency.h` | Out-of-line dependency functions with the same checks |
| `//08-sanitizer-errors:app` | Native program built with the selected sanitizer config |

`cc_library` and `cc_binary` are ordinary native rules. The sanitizer
`--config` options apply to both, so a report can come from either layer. The
source is not rebuilt differently between faults; `--source` and `--bug` choose
the code path at runtime.

## Build And Run A Control

Working directory for every command below: `forge/examples`.

```bash
../forge-bazel build --config=asan //08-sanitizer-errors:app
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  ./bazel-bin/08-sanitizer-errors/app --bug=none
```

The control must print `forge-san=43` and exit zero. `--config=ubsan` and
`--config=tsan` are separate builds. `--config=asan_ubsan` enables both, and
`--config=no_sanitizer` clears the effective sanitizer state without cleaning
the workspace.

## Trigger Faults

ASan heap access in business code and in the dependency:

```bash
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  ./bazel-bin/08-sanitizer-errors/app --bug=asan --input=8
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  ./bazel-bin/08-sanitizer-errors/app --source=dependency --bug=asan --input=8
```

Both must exit nonzero with an `AddressSanitizer: heap-buffer-overflow` report.
The first report names `BusinessAsan`; the second names
`forge_sanitizer_asan`.

UBSan signed overflow:

```bash
../forge-bazel build --config=ubsan //08-sanitizer-errors:app
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  ./bazel-bin/08-sanitizer-errors/app --bug=ubsan --input=2147483647
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  ./bazel-bin/08-sanitizer-errors/app --source=dependency \
  --bug=ubsan --input=2147483647
```

Both must report `runtime error: signed integer overflow` and exit nonzero.
For ASan+UBSan, use both options and both request orders:

```bash
../forge-bazel build --config=asan --config=ubsan //08-sanitizer-errors:app
../forge-bazel build --config=ubsan --config=asan //08-sanitizer-errors:app
```

`--config=asan_ubsan` is the canonical spelling. Do not pass sanitizer flags
through `copts` or `linkopts`; use the shared configs so all build paths agree.

TSan has a real race (`--bug=race`) and a synchronized control
(`--bug=synchronized`). Run it only if the host can initialize the TSan runtime;
a clean schedule is not evidence that a race was detected. Unsupported TSan
initialization is reported as skipped, not as a passing fault test.

## Clear Sanitizers

```bash
../forge-bazel build --config=asan_ubsan --config=no_sanitizer \
  //08-sanitizer-errors:app
readelf -d ./bazel-bin/08-sanitizer-errors/app | grep -E 'lib(asan|ubsan|tsan)' || true
./bazel-bin/08-sanitizer-errors/app --bug=none
```

The control must still print `forge-san=43`; the binary must not import a
sanitizer runtime or `__asan_`/`__ubsan_`/`__tsan_` symbols.

## Verify

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 08-sanitizer-errors/check.py
```

The checker runs clean controls and real business/dependency faults for ASan,
UBSan and both ASan+UBSan request orders, then verifies `no_sanitizer` cleared
the runtime and instrumentation. TSan is reported as skipped when the container
cannot initialize its runtime. Negative exits are asserted, never ignored.
