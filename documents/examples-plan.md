# Beginner Example Plan

Status: design only. This document proposes teaching projects; it does not
provide implemented example directories, source files, BUILD files, or a runnable
tutorial suite. Public API references remain in the [main guide](../README.md).

## Learning Goals

An introductory path should explain one new build concept at a time, preserve a
small recognizable program, and show an observable result. Readers should learn
what to declare, what Forge produces, how to consume it, and which evidence is
needed before deployment.

The first four lessons use equivalent runtime computation, such as mapping 20
to 41. This lets readers compare build paths without learning another business
problem. Dependencies must have real compiled symbols; empty archives or
header-only substitutes would hide the linking lesson.

## Workspace Design

The proposed location is one `examples/` Bazel workspace with one shared module
definition and rc import. Lesson packages have separate public targets and small
local sources, but no dependency on another lesson's generated output.

- Resolve Forge once and declare direct modules actually loaded by the examples.
- Use explicit labels for each lesson instead of a wildcard that includes
  environment-dependent targets or intentional failures.
- Keep workspace configuration visible; do not hide public Forge APIs behind a
  tutorial-only wrapper layer.
- Reuse one output base across lessons. Do not allocate a new temporary output
  base per lesson or command.
- Share only infrastructure, such as a tiny source-only Conan recipe index.
  Do not require a Conan server or public binary service for the introductory path.
- Ship reviewed locks and source digests. Normal builds must not require manual
  Conan cache preparation or alter user remotes.

Each lesson will have a short README covering prerequisites, its source/target
map, commands, expected results, inspection steps and cleanup. Only necessary
files belong in a lesson; fixtures for exhaustive negative testing stay in
`tests/fixtures`.

## Proposed Lessons

The directory names below are proposals, not links to existing projects.

| Order / proposed package | Main question | Public interfaces | Required observation |
| --- | --- | --- | --- |
| 01 `minimal-app` | How do I build and run a native program with Forge? | `eros_cc_binary`, native auto selection, Debug/Release | One real executable returns the expected result; unsupported host errors are understandable |
| 02 `native-library` | How does one target consume another? | `eros_cc_library`, `deps`, public headers | Program uses a compiled library without consumer-side include/link workarounds |
| 03 `cmake-library` | How does a CMake project become a native Bazel dependency? | `cmake_forge`, source filegroup, `install`, `exports` | Native consumer compiles, links and runs using only the exported dependency |
| 04 `conan-locked` | How do I consume a locked compiled third-party dependency? | `cmake_conan_forge`, file recipe index, lock and profiles | Missing binary builds from locked source, a real dependency symbol runs, and the lock/user cache stays unchanged |
| 05 `private-runtime` | Which files does a dynamically linked program need? | Shared-library forms, `data`, `eros_install_map`, runtime layout | Program finds a private library and unique resource from the collected layout without LD_LIBRARY_PATH |
| 06 `debian-package` | How do I turn a target into a private deb? | `pkg_eros_tar`, `pkg_eros_deb`, architecture/version inputs | Control fields match ELF, files have the intended private paths, and temporary-root extraction runs natively |
| 07 `release-symbols` | How do I debug optimized published code? | `separate_debug_info`, `eros_debug_info`, identity/source manifests | GDB resolves a real source breakpoint from the matching published binary and collected symbols |
| 08 `sanitizer-errors` | How do I prove business and dependency code are instrumented? | ASan first, then UBSan/TSan/combination and no_sanitizer | Actual runtime reports originate in each intended translation unit; independent clean controls pass |
| 09 `cross-build` | How do execution tools differ from the target ABI? | Explicit cross preset, host/build profiles, environment manifest | Correct target ELF/interpreter and actual compiler search paths are inspectable; absent target runtime stays unverified |
| 10 `multiarch-package` | How does one invocation produce distinct configured payloads? | `pkg_eros_deb_multiarch`, architecture/preset branches | Configuration graph, ELF, package metadata and per-branch provenance agree; no relabel-only result |

## Lesson Boundaries

### Native, CMake And Conan

Lessons 01-04 are the minimum useful first delivery. They build and run on the
supported native host; no robot, remote cache, GDB, binary server or cross SDK is
a prerequisite.

Lesson 03 starts with one installed static/PIC library and a public header.
Generated headers/public defines can be a clearly marked extension after the
basic consumer succeeds. It must explain source inputs versus installed exports.

Lesson 04 uses a supplied tiny recipe with a real out-of-line function and a
committed lock. A separate maintenance exercise may update the recipe/lock using
an explicit source. Precompiled-server setup and revision mutation are not part
of the first successful build.

### Runtime And Delivery

Lesson 05 starts with one shared dependency and one resource. A follow-up target
can add a SONAME chain, an indirect library and a dlopen-only plugin with its own
dependency. This makes the explicit runtime-root requirement visible without
forcing every beginner through plugins immediately.

Lesson 06 is self-contained rather than requiring a lesson 05 build artifact.
It shows version precedence and automatic native architecture selection. Default
commands inspect/extract the deb without sudo; clean target installation is a
separate acceptance scope, not an inference from extraction.

### Debug And Sanitizers

Lesson 07 keeps Release optimization. It distinguishes embedded DWARF, published
independent symbols and identity validation. A dependency-source variant can
extend it to Conan; target core collection belongs to CI rather than the initial
GDB exercise.

Lesson 08 defaults to an error-free run. Explicit runtime arguments trigger each
fault, without source edits between modes. ASan is the first exercise; UBSan,
TSan, both ASan/UBSan request orders and clearing state are subsequent exercises.
Expected negative exits must be checked, not suppressed with an unconditional
success command. A clean TSan schedule is not a successful fault detection.

### Cross And Multiple Configurations

Lessons 09-10 depend on the available execution toolchain and deployment
environment. Explain native execution, target architecture and SDK identity
before presenting commands.

Cross GCC defaults, CMake search roots and deployment loader/RPATH are different
concepts. Inspect the actual compiler/sysroot/headers/link directories. If the
matching SDK/runtime is absent, teach build/ELF inspection only and clearly
block deployment/run claims. Do not run cross programs automatically or teach
arbitrary glibc overrides as a shortcut.

On x86_64, a fully provisioned lesson 10 can show x86_64 plus ARM64. On ARM64,
native ARM64 plus cross ARM64 can teach split configurations, but must be called
two configurations, not two CPU architectures. Matching-target execution stays
a separate gate.

## Delivery Sequence

| Batch | Lessons | Entry gate |
| --- | --- | --- |
| A: first success and dependencies | 01-04 | Controlled native build environment and pinned local dependency inputs |
| B: useful delivery and diagnostics | 05-08 | Batch A concepts, native runtime, optional GDB/sanitizer prerequisites |
| C: platform-specific delivery | 09-10 | Compatible cross tools and explicit SDK/target validation prerequisites |

Do not bundle all batches into the first implementation. Complete and validate
one vertical lesson before expanding to the next concept.

## Acceptance For Implemented Lessons

Every implemented lesson will need reproducible commands, expected output/exit
codes, explicit source/dependency inputs and a short explanation of produced
files. Native execution, ELF inspection, temporary extraction and target execution
must remain separate assertions.

CI should build supported native lessons from the shared workspace and exercise
their positive/intentional-negative behavior with bounded time and parallelism.
Reports must identify skipped/blocked platform features. Do not create unbounded
output bases or require a full Forge acceptance run merely to read a lesson.

Cache-service provisioning, binary-revision adversarial tests, device scheduling,
cross-target cores and exhaustive failure injection belong to maintainer guides
and the [acceptance suite](test-design.md), not the beginner first-run path.

No example implementation is authorized by this planning document alone; the
project/source work remains a separate implementation step.
