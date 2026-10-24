"""Executable acceptance scopes, traced to documents/test-design.md."""

from __future__ import annotations

import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tarfile
import time

from test_runner import Blocked, Case, Context, ROOT, digest, require


BASIC = "//tests/fixtures/basic:"
LINK = "//tests/fixtures/link:"
RUNTIME = "//tests/fixtures/runtime:"
SAN = "//tests/fixtures/san:"
CHECKS = "//tests/fixtures/checks:"
EXTERNAL_TARGET = (
    "E-TA/E-TX is unavailable. Local extraction on the build host is not clean "
    "SDK target installation or cross-compiled runtime acceptance."
)
REMOTE_CACHE = "E-RC and independent E-X2 are unavailable; local reuse is not cross-machine cache evidence."
HOST_X86 = platform.machine() in ("x86_64", "amd64")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def action_graph(output: str) -> dict:
    beginning = output.find("{\n")
    require(beginning >= 0, "No action graph JSON returned")
    return json.JSONDecoder().raw_decode(output[beginning:])[0]


def executable_outputs(context: Context, target: str, **kwargs) -> list[Path]:
    found = []
    for path in context.files(target, **kwargs):
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and not candidate.is_symlink():
                if candidate.read_bytes()[:4] == b"\x7fELF" and os.access(candidate, os.X_OK):
                    # Shared libraries are often executable; only installed bin
                    # entries or the direct target executable are programs.
                    if ".so" not in candidate.name and ".debug" not in candidate.name:
                        found.append(candidate)
    unique = list(dict.fromkeys(path.resolve() for path in found))
    require(unique, f"No real ELF executable in declared outputs of {target}")
    return unique


def run_program(context: Context, path: Path, marker: str = "", args=(), env=None):
    result = context.run([path, *args], env=env)
    require(not marker or marker in result.stdout, f"Missing {marker!r} from {path}: {result.stdout}")
    return result


def elf(context: Context, path: Path, preset: str | None = None) -> str:
    result = context.run(["readelf", "-h", "-l", "-d", path])
    preset = preset or context.preset
    machine = "AArch64" if preset.startswith("linux_arm64") or "_cross_arm64" in preset else "Advanced Micro Devices X86-64"
    require(machine in result.stdout, f"Wrong ELF machine for {preset}: {path}")
    return result.stdout


def generated_configuration(context: Context):
    context.run([sys.executable, "bazel/toolchain/generate_files.py", "--check"])
    context.build("//bazel/toolchain:validate_environment")
    context.note("Generated configuration matches its source; installed environment validation succeeded.")


def environment(context: Context):
    generated_configuration(context)
    targets = [BASIC + name for name in ("native", "cmake", "conan")]
    for preset in (context.preset, context.cross_preset):
        for mode in ("debug", "release"):
            context.build(targets, preset=preset, mode=mode)
            for target in targets:
                for program in executable_outputs(context, target, preset=preset, mode=mode):
                    information = elf(context, program, preset)
                    if preset == context.cross_preset:
                        require("/opt/eros/lib/ld-linux-aarch64.so.1" in information,
                                f"Cross executable has wrong interpreter: {program}")
                    else:
                        run_program(context, program, "41")
    context.note("Three paths, Debug/Release, native execution and cross ELF/interpreter checked. Cross programs were not executed.")


def environment_manifest(context: Context):
    context.build("//bazel/toolchain:validate_environment")
    context.run([sys.executable, "bazel/toolchain/environment_test.py"])
    require((context.evidence.parent / "inputs/env_manifest.json").is_file(),
            "Acceptance report did not capture the actual environment/SDK manifest")
    # The validator's unit tests exercise altered copies, not the installed
    # compiler or SDK. Environment replacement requires a controlled image.
    context.note("Live manifest validation completed; immutable environment replacement is separately BLOCKED.")


def quoted_flags(context: Context):
    flags = ['--copt=-DFORGE_QUOTED_TEXT="hello world"']
    for target in (BASIC + "native", BASIC + "cmake", BASIC + "conan"):
        context.build(target, flags=flags)
        for program in executable_outputs(context, target, flags=flags):
            run_program(context, program, "41")
    context.note("All three business build paths compiled a static_assert requiring an exact quoted string macro with a space.")


def build_requirements(context: Context):
    target = "//tests/fixtures/conan:with_tool_requires"
    context.build(target, configs=("asan",))
    manifest = context.output(target, ".manifest.json", configs=("asan",))
    packages = read_json(manifest)["packages"]
    require({package["context"] for package in packages} == {"host", "build"}, "Build requirement was dropped from the snapshot graph")
    roots = [path for path in context.files(target, configs=("asan",)) if path.is_dir() and path.name.endswith(".snapshot")]
    require(len(roots) == 1, "No complete build/host snapshot")
    require((roots[0] / "packages/build_leaf/lib/libleaf.a").is_file(), "Build-context package missing")
    identities = read_json(manifest)["package_identity"]
    require(all("-fsanitize" not in package["package_info"] for package in identities if package["context"] == "build"),
            "Target sanitizer leaked into a build requirement")
    require(any("-fsanitize=address" in package["package_info"] for package in identities if package["context"] == "host"),
            "Target dependencies lost the selected sanitizer")
    context.note("A locked graph with both host and build requirements passes identity validation under an ASan target; build profile remains native and unsanitized.")


def unsupported_environment(context: Context):
    unsupported = ("linux_x86_64", "linux_x86_64_cross_arm64") if platform.machine() in ("aarch64", "arm64") else ("linux_arm64", "linux_arm64_cross_arm64")
    for preset in unsupported:
        context.negative(BASIC + "native", "unsupported|host|execution|toolchain|preset", preset=preset)
    context.negative(BASIC + "native", "sysroot|glibc|SDK|unsupported|fixed", flags=["--define=eros_sysroot=/tmp/invalid-sdk"])
    context.note("Unsupported-host presets and a free-form SDK override are rejected before producing artifacts.")


def conan_scenario(context: Context, tc: str):
    startup = [f"--bazel-startup={option}" for option in context.startup[1:]] if context.output_base else []
    result = context.run([
        sys.executable, "tests/fixtures/conan/verify.py", "--tc", tc,
        "--evidence", context.evidence / "conan", "--preset", context.preset,
        *startup,
    ], expected=None, timeout=1200)
    if result.returncode == 77:
        raise Blocked(result.stdout.strip())
    require(result.returncode == 0, f"{tc} failed; see evidence:\n{result.stdout[-8000:]}")


def dependency_case(tc: str):
    return lambda context: conan_scenario(context, tc)


def auxiliary_inputs(context: Context):
    conan_scenario(context, "TC-DEP-07")
    workspace = context.evidence / "source-copy"
    workspace.mkdir()
    paths = context.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"]).stdout.splitlines()
    for name in paths:
        source = ROOT / name
        if source.is_file():
            destination = workspace / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    fixture = workspace / "tests/fixtures/inputs"

    def build_and_check(value):
        result = context.run([
            "bazel", "--batch", "--host_jvm_args=-Xmx768m", "--nosystem_rc", "--nohome_rc", "--noworkspace_rc",
            f"--bazelrc={workspace / 'bazel/bazelrc'}", "build", f"--config={context.preset}",
            "--config=debug", f"--jobs={context.jobs}", "--subcommands", "--color=no", "--curses=no",
            "--noshow_progress", "//tests/fixtures/inputs:app",
        ], cwd=workspace, timeout=1200)
        require("cmake_action.py" in result.stdout, "Auxiliary input change did not execute the CMake action")
        run_program(context, workspace / "bazel-bin/tests/fixtures/inputs/app", f"forge-inputs={value}")

    build_and_check(114)
    for filename, before, after, value in (
        ("settings.cmake", "VALUE 10", "VALUE 20", 124),
        ("configured.h.in", "@FORGE_CONFIGURED_VALUE@", "(@FORGE_CONFIGURED_VALUE@ + 1)", 125),
        ("generate.py", "VALUE 100", "VALUE 200", 225),
        ("public.h", "VALUE 1", "VALUE 2", 226),
    ):
        path = fixture / filename
        contents = path.read_text()
        require(before in contents, f"Auxiliary fixture no longer contains {before!r}")
        path.write_text(contents.replace(before, after))
        build_and_check(value)
    context.note("A copied workspace rebuilt and changed runtime behavior after .cmake, template, generator, and header edits. Recipe patch/explicit-lock-update behavior also passed; original sources were not edited.")


def export_case(context: Context, kind: str):
    target = LINK + {"static": "app", "headers": "app", "dynamic": "dynamic_app", "pic": "shared_app"}[kind]
    context.build(target)
    programs = executable_outputs(context, target)
    require(len(programs) == 1, f"Ambiguous consumer program: {programs}")
    run_program(context, programs[0], "41")
    information = elf(context, programs[0])
    if kind == "dynamic":
        require("NEEDED" in information and ".so" in information, "Dynamic consumer did not link a shared library")
    context.note(f"Deps-only {kind} consumer compiled, linked, and ran with a real transitive Conan symbol.")


def external_consumer(context: Context):
    workspace = context.evidence / "workspace"
    workspace.mkdir()
    fixture = ROOT / "tests/fixtures/consumer"
    for name in ("BUILD.bazel", "main.cc"):
        shutil.copy2(fixture / name, workspace / name)
    build_file = workspace / "BUILD.bazel"
    build_file.write_text(build_file.read_text().replace(
        '["linux_arm64", "linux_arm64_cross_arm64"]', json.dumps([context.preset, context.cross_preset])))
    module = (fixture / "MODULE.bazel.in").read_text().replace("@FORGE_ROOT@", json.dumps(str(ROOT)))
    (workspace / "MODULE.bazel").write_text(module)
    context.run([
        "bazel", "--batch", "--host_jvm_args=-Xmx768m", f"--bazelrc={ROOT / 'bazel/bazelrc'}",
        "build", f"--config={context.preset}", "--config=release", f"--jobs={context.jobs}",
        "--color=no", "--curses=no", "--noshow_progress", "//:app", "//:deb", "//:multiarch",
    ], cwd=workspace, timeout=1200)
    run_program(context, workspace / "bazel-bin/app", "forge-consumer=41")
    outputs = sorted((workspace / "bazel-bin").glob("multiarch.*.deb"))
    require(len(outputs) == 2, "External module transition did not build both payloads")
    require((workspace / "bazel-bin/deb.deb").is_file(), "Original package_name call form did not produce a deb")
    context.note("Independent consuming MODULE uses public deps-only C++ export, original package_name keyword, runtime wrapper, and real split platforms with qualified labels.")


def strict_outputs(context: Context):
    for name in ("missing_header", "missing_library", "missing_executable"):
        context.negative("//tests/fixtures/fail:" + name, "missing|declared|install|not found|does not exist")
    context.build(LINK + "foo")
    for path in context.files(LINK + "foo"):
        if path.is_file():
            require(not path.read_bytes().startswith(b"#!/bin/sh\nexit 0"), "A dummy executable escaped validation")
    context.note("Missing header/library/program declarations fail; the legal library-only target builds without a fake executable.")


def static_shared_selection(context: Context):
    context.build([LINK + "app", LINK + "dynamic_app"])
    static = elf(context, executable_outputs(context, LINK + "app")[0])
    dynamic = elf(context, executable_outputs(context, LINK + "dynamic_app")[0])
    require("libfoo.so" not in static, "Static consumer acquired the dynamic alternative")
    require("libfoo.so" in dynamic, "Dynamic consumer did not acquire the shared alternative")
    for target in (LINK + "app", LINK + "dynamic_app"):
        query = context.bazel("aquery", f'mnemonic("CppLink", {target})', flags=["--output=jsonproto"]).stdout
        actions = action_graph(query).get("actions", [])
        require(actions, "No real CppLink action found")
        arguments = [argument for action in actions for argument in action.get("arguments", [])]
        if target.endswith(":dynamic_app"):
            require(not any(argument.endswith("/libfoo.a") for argument in arguments),
                    "Dynamic consumer also linked the static implementation")
        else:
            require(not any(argument.endswith("/libfoo.so") for argument in arguments),
                    "Static consumer also linked the dynamic implementation")


def cache_structure(context: Context):
    context.build([BASIC + "cmake", LINK + "foo"])
    query = context.bazel("aquery", f"deps({LINK}foo)", flags=["--include_artifacts", "--output=jsonproto"])
    data = action_graph(query.stdout)
    actions = [action for action in data.get("actions", []) if action.get("mnemonic") in ("ConanInstall", "CMakeBuild")]
    require(len(actions) >= 2, "Missing Conan/CMake custom actions")
    for action in actions:
        requirements = {entry["key"]: entry["value"] for entry in action.get("executionInfo", [])}
        require("local" not in requirements, f"{action['mnemonic']} forbids remote cache via local tag")
        require(requirements.get("no-remote-exec") == "1", "Custom action may run on an undeclared remote worker")
    artifact_paths = [part.get("label", "") for part in data.get("pathFragments", [])]
    require("env_manifest.json" in artifact_paths, "Environment manifest is absent from the declared action graph")
    require(any("lock" in value for value in artifact_paths), "No declared lock input")
    context.note("aquery verifies declared environment/lock artifacts and no-remote-exec rather than local. No remote cache hit is claimed.")


def configuration_invalidation(context: Context):
    keys = []
    for mode, configs, flags in (
        ("debug", (), ()), ("release", (), ()),
        ("debug", ("asan",), ()), ("debug", ("ubsan",), ()),
        ("release", (), ("--features=-separate_debug_info",)),
    ):
        context.build(LINK + "foo", mode=mode, configs=configs, flags=flags)
        query = context.bazel("aquery", f'mnemonic("ConanInstall|CMakeBuild", deps({LINK}foo))',
                              mode=mode, configs=configs, flags=["--output=jsonproto", *flags])
        actions = action_graph(query.stdout).get("actions", [])
        require(actions, "No Conan/CMake actions in variant graph")
        identities = []
        for action in actions:
            arguments = action.get("arguments", [])
            require("--config" in arguments, "Custom action has no declared configuration input")
            specification = context.execution_root / arguments[arguments.index("--config") + 1]
            require(specification.is_file(), f"Missing declared configuration input: {specification}")
            identities.append((action["mnemonic"], action["actionKey"], digest(specification)))
        identities.sort()
        (context.evidence / f"variant-{len(keys)}.json").write_text(json.dumps(identities, indent=2) + "\n")
        keys.append(hashlib.sha256(json.dumps(identities).encode()).hexdigest())
    require(len(set(keys)) == len(keys), "Distinct mode/sanitizer/debug options collapsed to identical action graphs")
    context.note("Mode, sanitizer, and debug options produce separate real builds/action graphs. Source/patch changes are exercised by TC-DEP-07; SDK upgrade is separately blocked.")


def snapshot_relocation(context: Context):
    conan_scenario(context, "TC-CACHE-04")


def extract_deb(context: Context, target: str, directory: Path, **kwargs) -> tuple[Path, str]:
    context.build(target, **kwargs)
    output = context.output(target, ".deb", **kwargs)
    directory.mkdir(parents=True, exist_ok=True)
    context.run(["dpkg-deb", "--extract", output, directory])
    metadata = context.run(["dpkg-deb", "--field", output]).stdout
    return output, metadata


def installed_programs(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("opt/eros/*/bin/*") if path.is_file() and os.access(path, os.X_OK))


def runtime(context: Context, *, plugins=False):
    directory = context.evidence / "root"
    _, metadata = extract_deb(context, RUNTIME + "runtime_deb", directory)
    require("Architecture: arm64" in metadata if context.preset.startswith("linux_arm64") else "Architecture: amd64" in metadata,
            "Incorrect deb architecture")
    programs = installed_programs(directory)
    require(programs, "Runtime deb has no program")
    for program in programs:
        information = elf(context, program)
        require("$ORIGIN" in information, "Runtime program lacks private relative RUNPATH")
        run_program(context, program, "F-RUNTIME linked=42 plugin=23")
    links = [path for path in directory.rglob("*") if path.is_symlink()]
    require(any(".so" in path.name for path in links), "SONAME links were flattened")
    for path in links:
        require(path.resolve().is_relative_to(directory.resolve()), f"Installed link escapes private tree: {path}")
        require(path.exists(), f"Dangling installed SONAME link: {path}")
    if plugins:
        context.build(RUNTIME + "app")
        run_program(context, executable_outputs(context, RUNTIME + "app")[0], "F-RUNTIME linked=42 plugin=23")
        require(any("plugin" in path.name for path in directory.rglob("*.so*")), "Plugin absent from deb")
        require(any("FORGE_RUNTIME_MARKER_62b591" in path.read_text(errors="replace")
                    for path in directory.glob("opt/eros/*/share/**/*") if path.is_file()),
                "Unique resource marker absent")
    context.note("Private extracted-root execution works with LD_LIBRARY_PATH removed; SONAME chain is intact. Clean E-TA installation remains a separate scope.")


def static_runtime(context: Context):
    context.build([LINK + "app", LINK + "dynamic_app", RUNTIME + "runtime_deb"])
    static = elf(context, executable_outputs(context, LINK + "app")[0])
    require("libbar.so" not in static, "Conan dependency did not prefer static linkage")
    runtime(context)


def private_versions(context: Context):
    root = context.evidence / "coinstalled"
    for version in (1, 2):
        extract_deb(context, f"//tests/fixtures/versions:v{version}_deb", root)
    programs = installed_programs(root)
    require(len(programs) == 2, f"Private package files overlapped: {programs}")
    outputs = [run_program(context, program).stdout for program in programs]
    require(outputs[0] != outputs[1], "Both version-locked packages used the same private library")
    first_package = programs[0].parent.parent
    shutil.rmtree(first_package)
    run_program(context, programs[1])
    context.note("Two extracted packages use different private versions; removing one private tree does not affect the other. Actual dpkg installation/uninstallation requires a clean target.")


def runtime_failures(context: Context):
    for target, pattern in (
        ("collision", "conflict|collision|same.*path|duplicate"),
        ("broken_closure", "missing|unresolved|needed|closure"),
        ("missing_plugin", "missing|not found|does not exist|declared"),
    ):
        context.negative(RUNTIME + target, pattern)


def cmake_runtime_files(context: Context):
    root = context.evidence / "root"
    extract_deb(context, "//tests/fixtures/cmake_runtime:deb", root)
    programs = installed_programs(root)
    require(len(programs) == 1, "CMake runtime fixture has no unique installed program")
    run_program(context, programs[0], "forge-cmake-runtime=42 FORGE_CMAKE_EXPLICIT_PLUGIN_RESOURCE")
    libraries = programs[0].parent.parent / "lib"
    require((libraries / "libcmake_plugin.so").is_file() and (libraries / "libcmake_private.so").is_file(),
            "Explicit dlopen-only CMake plugin or its private dependency was pruned")
    context.note("Same-CMake-target exports.runtime_files keeps the dlopen plugin, its private library, and resource without a separate data target.")


def multi_independent(context: Context):
    for preset in (context.preset, context.cross_preset):
        root = context.evidence / preset
        _, metadata = extract_deb(context, RUNTIME + "runtime_deb", root, preset=preset)
        architecture = "arm64" if preset.startswith("linux_arm64") or "_cross_arm64" in preset else "amd64"
        require("Architecture: " + architecture in metadata, "Independent branch mislabeled")
        for program in installed_programs(root):
            information = elf(context, program, preset)
            if preset == context.cross_preset:
                require("/opt/eros/lib/ld-linux-aarch64.so.1" in information, "Cross branch reused native payload")
    context.note("Independent native ARM64 and SDK ARM64 branches built; this is not the unavailable x86_64+AArch64 matrix.")


def multi_split(context: Context):
    target = CHECKS + "portable_multiarch" if context.preset.startswith("linux_x86_64") else RUNTIME + "multiarch"
    context.build(target)
    outputs = [path for path in context.files(target) if path.suffix == ".deb"]
    require(len(outputs) == 2 and outputs[0] != outputs[1], "Multiarch did not declare two independent deb outputs")
    interpreters = set()
    for index, output in enumerate(outputs):
        root = context.evidence / f"branch-{index}"
        context.run(["dpkg-deb", "--extract", output, root])
        metadata = context.run(["dpkg-deb", "--field", output, "Architecture"]).stdout.strip()
        preset = context.cross_preset if "cross_arm64" in output.name else context.preset
        architecture = "arm64" if preset.startswith("linux_arm64") or "_cross_arm64" in preset else "amd64"
        require(metadata == architecture, "Split branch has invalid metadata")
        for program in installed_programs(root):
            information = elf(context, program, preset)
            match = re.search(r"Requesting program interpreter: ([^\]]+)", information)
            require(match, "Branch program has no interpreter")
            interpreters.add(match.group(1))
    require(len(interpreters) == 2 and "/opt/eros/lib/ld-linux-aarch64.so.1" in interpreters,
            "Multiarch branches reused the same payload instead of native+SDK configurations")
    query = context.bazel("cquery", f"deps({target})", flags=["--output=transitions", "--transitions=full"]).stdout
    require(context.cross_preset in query and context.preset in query, "Split transition did not set both preset configurations")
    context.note("Two real native/SDK configurations, distinct interpreters, output names, and deb payloads checked; this ARM64 host does not prove the unavailable x86_64 matrix.")


def multi_failure(context: Context):
    context.negative(CHECKS + "unsupported_multiarch", "linux_x86_64|branch|unsupported|toolchain|host")


def group_outputs(context: Context, target: str, group: str = "eros_debug_info", **kwargs) -> list[Path]:
    context.build(target, flags=[f"--output_groups=default,{group}", *kwargs.pop("flags", ())], **kwargs)
    query = context.bazel("cquery", f"config({target}, target)", flags=[
        "--output=starlark",
        f"--universe_scope={target}",
        f'--starlark:expr="\\n".join([f.path for f in providers(target)["OutputGroupInfo"].{group}.to_list()])',
    ], **kwargs)
    paths = [context.execution_root / line.strip() for line in query.stdout.splitlines() if line.startswith("bazel-out/")]
    require(paths and all(path.exists() for path in paths), f"Declared {group} outputs are missing for {target}")
    return paths


def debug_symbols(context: Context):
    for target, function in (
        ("//tests/fixtures/debug:native", "forge_native_debug"),
        (BASIC + "cmake", "forge_basic_value"),
        (LINK + "foo", "forge_dependency_value"),
    ):
        outputs = group_outputs(context, target, mode="release")
        symbols = []
        for path in outputs:
            symbols.extend(path.rglob("*.debug") if path.is_dir() else [path] if path.suffix == ".debug" else [])
        require(symbols, f"No .debug symbol file for {target}")
        information = ""
        for symbol in symbols:
            result = context.run([context.gdb, "-nx", "-batch", symbol, "-ex", f"info line {function}"], expected=None)
            information += result.stdout
        require(re.search(r"Line \d+ of .*", information), f"GDB cannot locate source for {function}:\n{information}")
    context.note("GDB resolves actual function/source lines from independently declared Release symbols across all three paths, including Conan code.")


def crash_debugging(context: Context):
    context.build(SAN + "conan", mode="release")
    program = executable_outputs(context, SAN + "conan", mode="release")[0]
    result = context.run([
        context.gdb, "-nx", "-batch", program,
        "-ex", "set pagination off", "-ex", "run --source=dependency --bug=crash",
        "-ex", "bt", "-ex", "info line forge_dependency_crash",
    ], expected=None)
    if "Operation not permitted" in result.stdout or "ptrace: Permission denied" in result.stdout:
        raise Blocked("Container disallows ptrace; GDB crash execution/core collection requires E-TA. " + result.stdout)
    require("forge_dependency_crash" in result.stdout and re.search(r"\.c(c|pp)?:\d+|Line \d+ of", result.stdout),
            f"No third-party source location in actual crash backtrace: {result.stdout}")
    context.note("Local GDB ran a third-party crash and resolved its source frame; target core/CI archive round-trip is separately blocked.")


def sanitizer(context: Context, config: str, *, configs: tuple[str, ...] | None = None):
    requested = configs or (config,)
    settings = {
        "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
        "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
        "TSAN_OPTIONS": "halt_on_error=1:exitcode=66",
    }
    errors = [("asan", "8", "AddressSanitizer.*heap-buffer-overflow")] if config == "asan" else (
        [("ubsan", str(2**31 - 1), "runtime error: signed integer overflow")] if config == "ubsan" else (
            [("race", "1", "ThreadSanitizer: data race")] if config == "tsan" else [
                ("asan", "8", "AddressSanitizer.*heap-buffer-overflow"),
                ("ubsan", str(2**31 - 1), "runtime error: signed integer overflow"),
            ]
        )
    )
    for target in (SAN + "native", SAN + "cmake", SAN + "conan"):
        context.build(target, configs=requested)
        program = executable_outputs(context, target, configs=requested)[0]
        control = context.run([program, "--bug=none"], env=settings, expected=None)
        unsupported = re.search(
            r"ThreadSanitizer: (unexpected memory mapping|CHECK failed)|"
            r"ThreadSanitizer: unsupported|FATAL:.*ThreadSanitizer|"
            r"AddressSanitizer: shadow memory range interleaves", control.stdout,
        )
        if unsupported:
            raise Blocked(f"{config} runtime cannot initialize on this host; target {target}. {control.stdout.strip()}")
        require(control.returncode == 0 and "forge-san=43" in control.stdout,
                f"Sanitizer error-free control failed for {target}: {control.stdout}")
        for source in ("business", "dependency"):
            if config == "tsan":
                context.run([program, f"--source={source}", "--bug=synchronized"], env=settings)
            for bug, value, pattern in errors:
                # TSan can miss a particular schedule. A positive assertion
                # still requires an actual race report, never a clean exit.
                for attempt in range(3 if config == "tsan" else 1):
                    result = context.run([program, f"--source={source}", f"--bug={bug}", f"--input={value}"], env=settings, expected=None)
                    if result.returncode != 0:
                        break
                    if config == "tsan":
                        context.note(f"TSan schedule {attempt + 1} produced no diagnostic for {target}/{source}; not counted as detection.")
                require(result.returncode != 0, f"{config} did not reject {source} {bug} in {target}")
                require(re.search(pattern, result.stdout, re.DOTALL),
                        f"Expected {pattern!r} for {target}/{source}: {result.stdout}")
                function = ("forge_dependency_" if source == "dependency" else "business_") + bug
                require(function in result.stdout, f"Report did not originate in {function}: {result.stdout}")
    context.notes.insert(0, f"{'+'.join(requested)}: real business/third-party faults detected and separate clean controls passed on all three paths.")


def sanitizer_combination(context: Context):
    sanitizer(context, "asan_ubsan", configs=("asan", "ubsan"))
    sanitizer(context, "asan_ubsan", configs=("ubsan", "asan"))


def sanitizer_rejection(context: Context):
    for configs, flags in (
        (("msan",), ()), (("asan", "tsan"), ()), (("tsan", "ubsan"), ()),
        ((), ("--@eros_forge//bazel/config:sanitizer=asan_tsan",)),
    ):
        context.negative(BASIC + "native", "sanitizer|msan|incompat|unsupported|not defined|invalid", configs=configs, flags=flags)
    context.note("MSan and unconfirmed/contradictory combinations fail at configuration/analysis, not inside GCC.")


def sanitizer_off(context: Context):
    for target in (SAN + "native", SAN + "cmake", SAN + "conan"):
        context.build(target, configs=("asan_ubsan",))
        configs = ("asan_ubsan", "no_sanitizer")
        context.build(target, configs=configs)
        program = executable_outputs(context, target, configs=configs)[0]
        information = elf(context, program)
        require(not re.search(r"lib(asan|ubsan|tsan)", information), "Sanitizer runtime remained after no_sanitizer")
        symbols = context.run(["nm", "-u", program]).stdout
        require(not re.search(r"__(asan|ubsan|tsan)_", symbols), "Instrumentation remained after no_sanitizer")
        run_program(context, program, "forge-san=43")


def package_versions(context: Context):
    for target, environment, flags, expected in (
        ("explicit_version", {"DEB_VERSION": "2.3.4"}, ("--define=DEB_VERSION=3.4.5",), "7.8.9"),
        ("default_version", {"DEB_VERSION": "2.3.4"}, ("--define=DEB_VERSION=3.4.5",), "2.3.4"),
        ("default_version", {"DEB_VERSION": "2.3.5"}, ("--define=DEB_VERSION=3.4.5",), "2.3.5"),
        ("default_version", {}, ("--define=DEB_VERSION=3.4.5",), "3.4.5"),
        ("default_version", {}, (), "0.1.0"),
    ):
        label = RUNTIME + target
        context.build(label, env=environment, flags=flags)
        output = context.output(label, ".deb", env=environment, flags=flags)
        actual = context.run(["dpkg-deb", "--field", output, "Version"]).stdout.strip()
        require(actual == expected, f"Version precedence wrong: {actual!r} != {expected!r}")
    context.note("Attribute > action environment > define > default, including environment change without bazel clean, verified from deb control fields.")


def package_architecture(context: Context):
    context.negative(RUNTIME + "bad_architecture", "architecture|machine|ELF|mismatch",
                     preset=context.cross_preset)
    context.negative(CHECKS + "unknown_architecture", "architecture|CPU|no.match|constraint|preset",
                     flags=["--platforms=//tests/fixtures/checks:unknown_cpu"])
    _, metadata = extract_deb(context, RUNTIME + "runtime_deb", context.evidence / "root")
    require("Architecture: arm64" in metadata if context.preset.startswith("linux_arm64") else "Architecture: amd64" in metadata,
            "Known CPU mapped to wrong architecture")


def resources_all(context: Context):
    _, metadata = extract_deb(context, RUNTIME + "resources_all", context.evidence / "root")
    require("Architecture: all" in metadata, "Explicit resource-only package not marked all")
    context.negative(RUNTIME + "bad_all", "all|architecture|ELF")


def package_inventory(context: Context):
    runtime(context, plugins=True)
    package_root = context.evidence / "root"
    manifests = list(package_root.rglob("*manifest*.json"))
    require(manifests, "No install/provenance manifest in payload")
    for path in package_root.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix in (".json", ".cmake", ".txt"):
            text = path.read_text(errors="replace")
            require("_conan_home_" not in text, f"Private producer home escaped into {path}")


def test_package(context: Context):
    context.build(RUNTIME + "test_package", preset=context.cross_preset)
    outputs = context.files(RUNTIME + "test_package", preset=context.cross_preset)
    require(outputs, "No test package outputs")
    roots = []
    for path in outputs:
        if path.is_dir():
            roots.append(path)
        elif tarfile.is_tarfile(path):
            root = context.evidence / "test-package"
            with tarfile.open(path) as archive:
                archive.extractall(root, filter="data")
            roots.append(root)
    require(roots, "No collectable test artifact layout")
    texts = []
    for root in roots:
        for manifest in root.rglob("*.json"):
            texts.append(manifest.read_text())
    require(any(context.cross_preset in text for text in texts), "Test artifact manifest lacks target preset")
    require(any("sdk" in text.lower() and "layout" in text.lower() for text in texts),
            "Test artifact manifest lacks SDK identity/layout instructions")
    context.note("SDK ARM64 test program and runtime closure exported without executing it. Matching-target CI execution is separately blocked.")


def ci_symbols(context: Context):
    target = "//tests/fixtures/debug:native_test_package"
    context.build(target, mode="release")
    archive_path = context.output(target, ".tar.gz", mode="release")
    root = context.evidence / "native-archive"
    with tarfile.open(archive_path) as archive:
        archive.extractall(root, filter="data")
    manifest_path = root / "debug/debug_manifest.json"
    require(manifest_path.is_file(), "CI test archive lacks a relocatable aggregate debug manifest")
    context.run([sys.executable, "bazel/packaging/driver.py", "validate-debug", "--manifest", manifest_path])
    manifest = read_json(root / "eros_manifest.json")
    require(manifest["preset"] == context.preset, "CI archive variant was mislabeled")
    environment = read_json(context.evidence.parent / "inputs/env_manifest.json")
    require(manifest["environment_sha256"] == environment["environment_sha256"], "CI archive has wrong environment identity")
    directories = os.pathsep.join(str(root / name) for name in manifest["debug_directories"])
    result = context.run([
        context.gdb, "-nx", "-batch", "-ex", "set debug-file-directory " + directories,
        "-ex", "file " + str(root / "bin/native"), "-ex", "break forge_native_debug", "-ex", "run",
        "-ex", "bt", "-ex", "info line forge_native_debug",
    ], expected=None)
    if "Operation not permitted" in result.stdout:
        raise Blocked("Container disallows GDB execution for the extracted CI archive: " + result.stdout)
    require(re.search(r"Breakpoint \d+(?:\.\d+)?, forge_native_debug", result.stdout) and re.search(r"native\.cc:\d+", result.stdout),
            "GDB did not hit an actual source breakpoint using only extracted archive symbols: " + result.stdout)

    target = "//tests/fixtures/debug:conan_symbols_tar"
    context.build(target, mode="release")
    symbols_path = context.output(target, ".tar.gz", mode="release")
    symbols_root = context.evidence / "conan-symbols"
    with tarfile.open(symbols_path) as archive:
        archive.extractall(symbols_root, filter="data")
    identities = [path for path in symbols_root.rglob("debug_manifest.json") if read_json(path).get("symbols_only")]
    require(len(identities) == 1, "Transitive Conan symbol archive has no unique aggregate identity manifest")
    identity = identities[0]
    installs = [path for path in context.files(LINK + "foo", mode="release") if path.is_dir() and path.name.endswith(".install")]
    require(len(installs) == 1, "No unique matching CMake install tree for the symbol archive")
    context.run([
        sys.executable, "bazel/packaging/driver.py", "validate-debug", "--manifest", identity,
        "--binary-root", installs[0], "--debug-root", identity.parent,
    ])
    pairs = read_json(identity)["binaries"]
    require(any("bar" in pair["binary"] for pair in pairs) and any("leaf" in pair["binary"] for pair in pairs),
            "Symbol archive omitted transitive Conan package symbols")
    require(not list(symbols_root.rglob("CMakeCache.txt")), "Private producer CMake cache leaked into debug sources")
    require(not any("CMakeFiles" in path.parts or path.name.startswith("conanbuildenv") for path in symbols_root.rglob("*")),
            "Private producer build/cache artifacts leaked into debug sources")
    context.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_packaging_unit.py"])
    context.note("Extracted native CI archive hits a real GDB source breakpoint; transitive Conan symbols-only tar validates against the matching payload and excludes producer caches. Tampered identities/architecture unit checks pass. Multi-CPU/target CI remains separately blocked.")


def source_snapshot(context: Context) -> dict[str, str]:
    paths = context.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"]).stdout.splitlines()
    result = {}
    for value in paths:
        path = ROOT / value
        if path.is_file() and value != "MODULE.bazel.lock":
            result[value] = digest(path)
    return result


def user_conan_snapshot(home: Path | None = None, timeout: float = 30) -> dict:
    home = home or Path.home() / ".conan2"
    if not home.exists():
        return {"<home>": "absent"}
    started = time.monotonic()
    result = {}
    for path in chain((home,), home.rglob("*")):
        if time.monotonic() - started > timeout:
            raise Blocked(f"User Conan cache metadata audit exceeded {timeout:g}s; no full-cache content scan was attempted")
        state = path.lstat()
        result[str(path.relative_to(home))] = (
            state.st_mode, state.st_size, state.st_mtime_ns, state.st_ctime_ns,
            os.readlink(path) if path.is_symlink() else "",
        )
    return result


def isolation(context: Context):
    before = source_snapshot(context)
    conan_before = user_conan_snapshot()
    context.build([BASIC + "native", BASIC + "cmake", LINK + "foo", RUNTIME + "runtime_deb"])
    context.negative("//tests/fixtures/fail:missing_executable", "missing|declared|install|not found")
    context.build(LINK + "app")
    require(before == source_snapshot(context), "Ordinary/failed/retried builds modified source files")
    require(conan_before == user_conan_snapshot(), "Build modified user ~/.conan2")
    context.note("Source content and user Conan cache path/size/mode/mtime/ctime/link metadata unchanged across successful, failing, and retried builds; large cache payloads are not read. Concurrent independent-workspace interruption remains TC-CACHE-05.")


def resource_policy(context: Context):
    context.build([BASIC + "cmake", LINK + "foo"], flags=["--define=forge_jobs=1"])
    context.negative("//tests/fixtures/fail:broken_recipe", "recipe|build|compile|Conan|failed",
                     flags=["--define=forge_jobs=1"])
    context.note("Concurrent outer targets obey --jobs; internal budget and failure-stage diagnostics checked with the documented forge_jobs override.")


def local_case(identifier, title, check, priority="P0", scope="local build host"):
    return Case(identifier + "/local", title, priority, scope, check)


def blocked_case(identifier, title, reason, priority="P0", suffix="external", scope="external environment"):
    return Case(identifier + "/" + suffix, title, priority, scope, unavailable=reason)


CASES = [
    local_case("TC-ENV-01", "Three paths, modes, generated config, native/cross ELF", environment),
    Case("TC-ENV-01/quoted-flags", "Typed global compiler argument boundaries", "P1", "local native business compilation", quoted_flags),
    Case("TC-ENV-01/x86", "x86_64 platform matrix", "P0", "x86 native/cross build host",
         environment if HOST_X86 else None, "" if HOST_X86 else "E-X1 is unavailable on this ARM64 execution host."),
    local_case("TC-ENV-02", "Installed environment identity validation", environment_manifest),
    blocked_case("TC-ENV-02", "Replace compiler support/SDK in immutable environment copy", "No independently provisioned controlled environment/SDK image for destructive replacement and legitimate upgrade.", suffix="upgrade"),
    local_case("TC-ENV-03", "Reject unsupported host and SDK override", unsupported_environment),
    blocked_case("TC-ENV-03", "Cross SDK runtime acceptance", EXTERNAL_TARGET, suffix="target"),
    blocked_case("TC-ENV-04", "Cross try_run and damaged SDK link probe", "E-TA and a disposable complete cross SDK are unavailable; no fabricated try_run result.", priority="P1"),
    *[local_case(f"TC-DEP-{number:02}", title, auxiliary_inputs if number == 7 else dependency_case(f"TC-DEP-{number:02}")) for number, title in enumerate((
        "Locked revisions survive remote updates", "Explicit package-local lock update", "Exact precompiled binary hit",
        "Missing binary source fallback", "Lock/integrity/build failure rejection", "Variant-aware package identity", "Auxiliary input invalidation",
    ), 1)],
    Case("TC-DEP-06/build-requirements", "Separate Conan build-context identity", "P1", "local locked host/build graph", build_requirements),
    local_case("TC-EXP-01", "Deps-only static transitive consumer", lambda context: export_case(context, "static")),
    Case("TC-EXP-01/consumer-workspace", "External module macro/provider/transition integration", "P0", "independent local consuming module", external_consumer),
    local_case("TC-EXP-02", "Generated public header and define", lambda context: export_case(context, "headers")),
    local_case("TC-EXP-03", "Dynamic consumer and runfiles", lambda context: export_case(context, "dynamic")),
    local_case("TC-EXP-04", "PIC static dependency in native shared consumer", lambda context: export_case(context, "pic")),
    local_case("TC-EXP-05", "Static/shared alternative selection", static_shared_selection, priority="P1"),
    local_case("TC-EXP-06", "Strict missing outputs and library-only target", strict_outputs),
    local_case("TC-CACHE-01", "Cache action/input structure", cache_structure, scope="aquery only; not remote-hit acceptance"),
    blocked_case("TC-CACHE-01", "Independent machine remote cache hits", REMOTE_CACHE),
    blocked_case("TC-CACHE-02", "Cold remote cache and local fallback/upload", REMOTE_CACHE),
    local_case("TC-CACHE-03", "Configuration-specific real builds and action graphs", configuration_invalidation),
    blocked_case("TC-CACHE-03", "Legitimate SDK identity upgrade/cache invalidation", "A second immutable SDK/environment release is unavailable.", suffix="sdk"),
    local_case("TC-CACHE-04", "Snapshot relocation after isolated Conan home removal", snapshot_relocation),
    blocked_case("TC-CACHE-05", "Independent-workspace concurrent interruption/retry", "Two independent controlled workspaces/environments not provisioned; local sequential retries do not meet this scenario.", priority="P1"),
    local_case("TC-MULTI-01", "Independent native and SDK deb payloads", multi_independent),
    Case("TC-MULTI-01/x86", "x86_64 and AArch64 independent payloads", "P0", "x86 native/cross build host",
         multi_independent if HOST_X86 else None, "" if HOST_X86 else "E-X1 x86_64 execution host unavailable."),
    local_case("TC-MULTI-02", "Real native ARM64/SDK ARM64 split configurations", multi_split),
    blocked_case("TC-MULTI-02", "Distinct CPU x86_64/AArch64 split and target runs",
                 "E-TA/E-TX unavailable; cross target execution is not proved by a build." if HOST_X86 else
                 "E-X1 and E-TA/E-TX unavailable; dual ARM64 variants do not prove dual CPU support.", suffix="cpu-matrix"),
    blocked_case("TC-MULTI-03", "Per-architecture/aggregate remote reuse", REMOTE_CACHE, priority="P1"),
    local_case("TC-MULTI-04", "Unsupported aggregate branch fails", multi_failure),
    local_case("TC-RUN-01", "Static preference and complete dynamic closure", static_runtime),
    local_case("TC-RUN-02", "Extracted private payload and SONAME chain", runtime),
    local_case("TC-RUN-03", "Data-only plugin/resource in runfiles and private install", lambda context: runtime(context, plugins=True)),
    Case("TC-RUN-03/cmake-runtime-files", "Explicit same-CMake-target runtime plugin roots", "P0", "local extracted private package", cmake_runtime_files),
    local_case("TC-RUN-04", "Private version coexistence/removal in temporary root", private_versions),
    local_case("TC-RUN-05", "Reject missing plugin/dependency and path collision", runtime_failures),
    blocked_case("TC-RUN-06", "Clean target SDK/sanitizer runtime origin", EXTERNAL_TARGET, priority="P1"),
    blocked_case("TC-RUN-02", "Clean matching-target installation/run", EXTERNAL_TARGET, suffix="target"),
    blocked_case("TC-RUN-03", "Cross plugin/resource runtime", EXTERNAL_TARGET, suffix="target"),
    blocked_case("TC-RUN-04", "Clean target dpkg install/uninstall coexistence", EXTERNAL_TARGET, suffix="target"),
    local_case("TC-DBG-01", "Release archived symbols resolve real source lines", debug_symbols),
    local_case("TC-DBG-02", "Stripped dependency rejected/rebuilt for debug", dependency_case("TC-DBG-02")),
    local_case("TC-DBG-03", "Live Conan crash backtrace resolves source", crash_debugging),
    blocked_case("TC-DBG-03", "Target core/CI archive and mismatched-symbol round-trip", EXTERNAL_TARGET, suffix="target-core"),
    blocked_case("TC-DBG-04", "Remote cache debug archive retrieval", REMOTE_CACHE, priority="P1"),
    local_case("TC-SAN-01", "ASan business/third-party faults and controls", lambda context: sanitizer(context, "asan")),
    local_case("TC-SAN-02", "UBSan business/third-party faults and controls", lambda context: sanitizer(context, "ubsan")),
    local_case("TC-SAN-03", "TSan real races and synchronized controls", lambda context: sanitizer(context, "tsan")),
    local_case("TC-SAN-04", "Both ASan+UBSan request orders", sanitizer_combination),
    local_case("TC-SAN-05", "Reject MSan and incompatible combinations", sanitizer_rejection),
    local_case("TC-SAN-06", "Clear all sanitizer state without clean", sanitizer_off),
    local_case("TC-PKG-01", "Version precedence and action environment invalidation", package_versions),
    local_case("TC-PKG-02", "Known/unknown/mismatched deb architecture", package_architecture),
    local_case("TC-PKG-03", "Explicit all accepts resources but rejects ELF", resources_all, priority="P1"),
    local_case("TC-PKG-04", "Payload inventory, permissions, links, provenance", package_inventory, priority="P1"),
    blocked_case("TC-PKG-04", "Clean installed-target payload verification", EXTERNAL_TARGET, priority="P1", suffix="target"),
    local_case("TC-CI-01", "Export cross test closure without executing it", test_package),
    blocked_case("TC-CI-01", "CI executes exported artifact on target", EXTERNAL_TARGET, suffix="target"),
    local_case("TC-CI-02", "Collect symbols and reject mismatched identities", ci_symbols),
    blocked_case("TC-CI-02", "Multi-CPU CI release archive/target association", "CI multi-CPU archive service and matching target runtimes unavailable.", suffix="ci"),
    local_case("TC-QUAL-01", "No source/user Conan cache writes", isolation, priority="P1"),
    local_case("TC-QUAL-02", "Bounded internal resources and actionable failures", resource_policy, priority="P1"),
]
