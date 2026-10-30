# Beginner Example Roadmap

Status: Batch A (lessons 01-04) and Batch B (lessons 05-08) are implemented in
the shared [examples workspace](../examples/README.md). Batch A's `check.py`
builds and runs the native lessons in Debug/Release; each Batch B lesson has its
own `check.py` for its runtime, packaging, symbol or sanitizer evidence. In Batch
C, lesson 09 is implemented for cross builds and static inspection only; it does
not deploy or execute target artifacts. Lesson 10 remains planned.
Public API references are in the [main guide](../README.md).
An independent [two-deb extension](../examples/README.md#two-debian-packages-b-depends-on-a)
shows a real first-party package dependency; it is not a prerequisite for the
implemented lesson 06.

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

The location is one `examples/` Bazel workspace with one shared module
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

## Lessons And Implementation Status

Lessons 01-09 link to implemented projects; lesson 09 is build-only. Lesson 10
describes planned work and does not have an example directory yet.

| Order / package | State | Main question | Public interfaces | Required observation |
| --- | --- | --- | --- | --- |
| [01 minimal-app](../examples/01-minimal-app/README.md) | Implemented | How do I build and run a native program with Forge? | `eros_cc_binary`, native auto selection, Debug/Release | One real executable returns the expected result |
| [02 native-library](../examples/02-native-library/README.md) | Implemented | How does one target consume another? | `eros_cc_library`, `deps`, public headers | Program uses a compiled library without consumer-side include/link workarounds |
| [03 cmake-library](../examples/03-cmake-library/README.md) | Implemented | How does a CMake project become a native Bazel dependency? | `cmake_forge`, source filegroup, `install`, `exports` | Native consumer compiles, links and runs using only the exported dependency |
| [04 conan-locked](../examples/04-conan-locked/README.md) | Implemented | How do I consume a locked compiled third-party dependency? | `cmake_conan_forge`, file recipe index, lock and profiles | Locked source builds, a real dependency symbol runs, and source/lock/cache audits pass |
| [05 private-runtime](../examples/05-private-runtime/README.md) | Implemented | Which files does a dynamically linked program need? | Shared-library forms, `data`, `eros_install_map`, runtime layout | Private library/resource resolve without LD_LIBRARY_PATH |
| [06 debian-package](../examples/06-debian-package/README.md) | Implemented | How do I turn a target into a private deb? | `pkg_eros_tar`, `pkg_eros_deb`, architecture/version inputs | Metadata matches ELF; private layout works after native extraction |
| 06b `deb-dependency` | Implemented extension | How does B build against A but load A from a separate deb? | `pkg_eros_deb(srcs, depends)`, versioned SONAME and relative RUNPATH | A owns its library, B owns its executable; absent/present/removed A changes B's behavior |
| [07 release-symbols](../examples/07-release-symbols/README.md) | Implemented | How do I debug optimized published code? | `separate_debug_info`, `eros_debug_info`, identity/source manifests | GDB resolves a real source breakpoint using matching symbols |
| [08 sanitizer-errors](../examples/08-sanitizer-errors/README.md) | Implemented | How do I prove business and dependency code are instrumented? | ASan, UBSan/TSan/combination and no_sanitizer | Real reports and independent clean controls |
| [09 cross-build](../examples/09-cross-build/README.md) | Implemented (build-only) | How do execution tools differ from the target ABI? | Cross preset, host/build profiles, environment manifest | Debug/Release ARM64 ELF, libraries, compiler paths and profiles inspected; no target execution or deployment |
| 10 `multiarch-package` | Planned | How does one invocation produce distinct configured payloads? | `pkg_eros_deb_multiarch`, architecture/preset branches | Configurations, ELF, metadata and provenance agree |

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

Lesson 05 uses one shared dependency, one resource and a versioned SONAME chain.
A follow-up target can add an indirect library and a dlopen-only plugin with its
own dependency. This makes the explicit runtime-root requirement visible without
forcing every beginner through plugins immediately.

Lesson 06 is self-contained rather than requiring a lesson 05 build artifact.
It shows version precedence and automatic native architecture selection. Default
commands inspect/extract the deb without sudo; clean target installation is a
separate acceptance scope, not an inference from extraction.

The separate 06b extension has a true first-party shared-library boundary: B
builds with A in Bazel, B.deb declares an exact version dependency on A.deb,
derived from the selected A.deb instead of a hard-coded B version, and B.deb
does not duplicate A's shared library. Its native extraction and
isolated `dpkg` checks do not claim clean target installation or target ABI
validation.

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
If the local container cannot initialize the TSan runtime, report a skip rather
than turning an unobserved race into a pass.

### Cross And Multiple Configurations

Lesson 09 needs the controlled x86_64 execution environment and ARM64 cross
tools, not a target device or an installed deployment runtime. It cross-builds a
native-rule consumer and a real CMake/Conan static dependency, checks both Conan
profiles and the environment identity, and inspects the resulting ELF files.
It does not execute the program or deploy anything, even if a runtime is present.
Lesson 10 remains planned. Explain execution CPU, target architecture and SDK
identity before presenting its commands.

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

| Batch | Lessons | State | Entry gate |
| --- | --- | --- | --- |
| A: first success and dependencies | 01-04 | Implemented | Controlled native build environment and pinned local dependency inputs |
| B: useful delivery and diagnostics | 05-08 | Implemented | Batch A concepts, native runtime, GDB and sanitizer checks |
| C: platform-specific delivery | 09-10 | 09 implemented (build-only); 10 planned | Compatible cross tools for builds; target execution/deployment remain separate scopes |

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

Implementing lesson 10 is a separate scoped step. Keep lesson 09's build-only
evidence distinct from native runs and from target execution/deployment acceptance.
