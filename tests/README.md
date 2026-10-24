# Forge Acceptance Tests

The [acceptance design](../documents/test-design.md) defines TC cases and
evidence requirements. The runner executes explicit scopes; fixtures validate
rules and are not a beginner tutorial collection.

## Commands

Run from the Forge repository root:

```bash
./forge-shell
# The following commands run inside the container:
python3 tests/test_runner.py --list
python3 tests/test_runner.py --tc TC-SAN-01 --report /tmp/kilo/forge-asan.md
python3 tests/test_runner.py --all --strict --report /tmp/kilo/forge-release.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*_unit.py'
python3 bazel/toolchain/environment_test.py
python3 bazel/packaging/driver_test.py
python3 bazel/toolchain/generate_files.py --check
```

On the host, run the launcher unit tests with
`python3 -m unittest discover -s tests -p test_container_entry.py`.
Set `FORGE_TEST_DOCKER=1` for its isolated Docker integration case; that case
creates and removes only its uniquely named test container. The existing
runner's new environment/entry/CI design cases are not all registered yet;
do not treat `--all --strict` as an available full release gate.
The runner records the launcher-provided local image ID as a caller claim;
if an image claim is present but the captured Bazel environment is missing or
does not match, it writes a failed provenance report and exits nonzero.

`--tc` is repeatable. A base ID selects all its scopes; a complete ID such as
`TC-ENV-01/local` selects only that scope. Unknown IDs and empty selections fail.
`--preset` defaults to the supported native host preset. `--jobs` bounds outer
Bazel actions; direct Bazel builds use `--define=forge_jobs=N` for internal
CMake/Conan parallelism.

## Tool Prerequisites

Use the controlled compiler/tool environment and a matching native runtime for
local execution. Cross execution requires the matching target SDK/runtime.

For binary/revision scenarios, explicitly prepare an isolated test server:

```bash
python3 tests/fixtures/conan/verify.py --tc TC-DEP-03 --evidence /tmp/kilo/forge-server-check --preset linux_arm64 --bootstrap-server
```

This downloads `conan-server==2.33.0` to `/tmp/kilo/forge-conan-server`, creates a
loopback-only server with disposable data and stops it on completion. A file
recipe index is source-only, not a binary/revision server. Ordinary dependency
builds do not require this server or contact PyPI.

Use installed GDB, `--gdb PATH`, or `FORGE_GDB`. On supported Ubuntu hosts an
isolated debugger can be extracted without system installation:

```bash
python3 tests/bootstrap_debugger.py --output /tmp/kilo/forge-gdb
python3 tests/test_runner.py --tc TC-DBG-01 --gdb /tmp/kilo/forge-gdb/gdb
```

The bootstrap records exact APT candidate versions and archive digests. Its
wrapper does not export `LD_LIBRARY_PATH` to tested programs. Reports capture
the selected debugger's version and executable digest.

## Results And Evidence

| State | Meaning |
| --- | --- |
| PASS | All assertions for the named scope passed |
| FAIL | A command, output, diagnostic or behavior violated the scope |
| SKIP | The scope does not apply to the selected platform |
| BLOCKED | Environment or external execution/evidence prerequisites are unavailable |

Any FAIL returns `1`. Without failures the runner returns `0`, or `2` with
`--strict` when the selected scopes are incomplete. Argument errors return `2`.
Exit zero without strict mode is not full release acceptance.

Each invocation has a new evidence directory under `/tmp/kilo`; `--evidence`
can select a new/empty directory outside source. `--report` selects a text or
JSON report, including a persistent ignored `.forge-evidence/` report path.
Markdown/text reports have a neighboring JSON report.

The runner announces active scopes and checkpoints before/after each case.
`run_complete`, expected/recorded scope counts and `active_scope` expose
interruption. Each case has a result JSON and complete command logs with argv,
cwd, selected environment, duration and exit code. Pending scopes are not passes.
Provenance captures source/lock digests and the actual environment/SDK manifest.

Normal programs must exit successfully. Sanitizer checks require a real
diagnostic at the business and dependency functions plus successful independent
controls. TSan allows at most three independent schedules; a clean schedule is
a nondetection, not a pass. Unexpected crashes/diagnostics are not retried into
success.

## Output Bases And Resources

Each invocation creates its own Bazel output base under the evidence directory,
uses a bounded JVM and shuts the server down after execution. Artifact lookup
uses its actual execroot, not mutable workspace `bazel-bin` symlinks.

**Shutdown does not delete the output base.** File-by-file tool inputs, external
repositories and sandbox trees can consume many inodes even with free bytes.
Before repeated suites inspect `df -h`, `df -i` and output-base inode usage;
limit retained runs and archive the required logs/artifacts before cleanup.

Recover only a known task-owned base, identified by
`input_provenance.bazel_output_base` in its report, using
`bazel --batch --output_base=/absolute/task-owned/base clean --expunge`.
Do not delete arbitrary shared caches or replace resource management with a
higher `--jobs` value. Whole-suite runs should be deliberate, not repeated for
documentation-only changes.

The source audit uses file hashes. The user Conan cache audit uses paths, sizes,
modes, mtime, ctime and links without reading all package payloads. Each cache
audit has a 30-second deadline; expiration is BLOCKED, not an unbounded wait.

## Fixtures And Environment Scopes

| Directory | Contract |
| --- | --- |
| `fixtures/basic` | Three build paths and equivalent computation |
| `fixtures/link` | Headers/defines, real transitive links, static/shared/PIC consumers |
| `fixtures/conan` | Controlled recipes, locks, revisions, binary hits and source fallback |
| `fixtures/inputs` | CMake/template/generator/header invalidation in copied source |
| `fixtures/consumer` | Independent module integration and transition labels |
| `fixtures/runtime` | Shared chains, SONAME links, data-only plugin/resources |
| `fixtures/cmake_runtime` | Same-target explicit CMake runtime roots |
| `fixtures/versions` | Private package version coexistence |
| `fixtures/debug` | Real source frames, symbols and archives |
| `fixtures/san` | Runtime-triggered faults and clean/synchronized controls |
| `fixtures/fail`, `fixtures/checks` | Strict failures, unknown CPU and unsupported branches |

Native programs may run only in compatible environments. Temporary-root deb
extraction checks private layout, not clean target installation/uninstallation.
Cross ELF/interpreter checks do not prove target glibc agreement or execution.
Two ARM64 variants do not prove an x86_64/AArch64 CPU matrix.

Independent-host cache, controlled SDK replacement, target core and CI execution
scopes require their stated environments and evidence integration. Merely
registering a scope or provisioning a cache endpoint is not a completed test.
Use the [acceptance design](../documents/test-design.md) for release gates.
