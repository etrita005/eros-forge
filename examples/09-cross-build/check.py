#!/usr/bin/env python3
"""Build and inspect ARM64 artifacts on x86_64; never run or deploy them."""

import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess


LESSON = Path(__file__).resolve().parent
WORKSPACE = LESSON.parent
TARGET = "//09-cross-build:app"
PRESET = "linux_x86_64_cross_arm64"


def run(*arguments, stderr=False):
    print("CHECK " + shlex.join(str(arg) for arg in arguments), flush=True)
    env = dict(os.environ, LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    result = subprocess.run(arguments, cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f"Command exited {result.returncode}: {result.stdout}{result.stderr}")
    return (result.stderr if stderr else result.stdout).strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot():
    paths = [WORKSPACE / name for name in ("MODULE.bazel", "MODULE.bazel.lock", ".bazelrc")]
    for root in (LESSON, WORKSPACE / "_support"):
        paths.extend(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    return {str(path.relative_to(WORKSPACE)): digest(path) for path in paths}


def check_mode(mode, execution_root):
    options = [f"--config={PRESET}", f"--config={mode}", "--color=no", "--curses=no", "--noshow_progress"]
    run("bazel", "build", *options, TARGET)

    def files(expression):
        output = run("bazel", "cquery", *options, expression, "--output=files")
        return [execution_root / line for line in output.splitlines()]

    def single(paths):
        require(len(paths) == 1 and paths[0].is_file(), f"Expected one declared file, got {paths}")
        return paths[0]

    binary = single(files(f"config({TARGET}, target)"))
    env_path = single(files(f'filter("env_manifest.json$", deps(config({TARGET}, target)))'))
    environment = json.loads(env_path.read_text())
    require(environment["host"]["cpu"] == "x86_64", "Expected an x86_64 execution environment")
    cross = environment["toolchains"]["cross_arm64"]
    native = environment["toolchains"]["native"]
    tools = cross["tools"]
    compiler = tools["gcc"]["path"]
    require(cross["target_triple"] == run(compiler, "-dumpmachine") == "aarch64-linux-gnu",
            "Compiler target does not match the ARM64 environment manifest")
    require(run(compiler, "-dumpfullversion", "-dumpversion") == tools["gcc"]["version"],
            "Compiler version differs from the captured environment")
    require(run(compiler, "-print-sysroot") == cross["sysroot"], "Compiler sysroot changed")
    search_dirs = run(compiler, "-print-search-dirs")
    libraries = re.search(r"^libraries: =(.*)$", search_dirs, re.MULTILINE)
    require(libraries, "Compiler did not report its library search directories")
    library_dirs = sorted({str(Path(path).resolve()) for path in libraries.group(1).split(":") if Path(path).is_dir()})
    require(library_dirs and library_dirs == cross["library_search_dirs"], "Compiler library search paths changed")
    preprocessing = run(tools["g++"]["path"], "-E", "-x", "c++", "-v", "/dev/null", stderr=True)
    includes = re.search(r"#include <\.\.\.> search starts here:\n(.*?)\nEnd of search list\.",
                         preprocessing, re.DOTALL)
    require(includes, "Compiler did not report its header search directories")
    include_dirs = [str(Path(line.strip()).resolve()) for line in includes.group(1).splitlines()]
    require(include_dirs and include_dirs == cross["builtin_includes"], "Compiler header search paths changed")
    compiler_header = run(tools["readelf"]["path"], "-hW", compiler)
    require("Advanced Micro Devices X86-64" in compiler_header, "Cross compiler must execute on x86_64")

    header = run(tools["readelf"]["path"], "-hW", binary)
    require(re.search(r"Machine:\s+AArch64", header) and re.search(r"Class:\s+ELF64", header),
            "Program is not an ELF64 AArch64 artifact")
    segments = run(tools["readelf"]["path"], "-lW", binary)
    interpreter = re.search(r"Requesting program interpreter:\s*([^\]]+)", segments)
    require(interpreter and interpreter.group(1) == environment["sdk"]["dynamic_interpreter"],
            "Program interpreter differs from the cross preset")
    dynamic = run(tools["readelf"]["path"], "-dW", binary)
    runpaths = re.findall(r"\((?:RUNPATH|RPATH)\).*?\[([^\]]+)\]", dynamic)
    require(environment["sdk"]["path"] + "/lib" in ":".join(runpaths).split(":"),
            "Program is missing the cross preset's runtime search path")
    symbols = run(tools["nm"]["path"], "-C", "--defined-only", binary)
    for symbol in ("cross_math::transform(int)", "tiny_math::transform(int)"):
        require(symbol in symbols, f"Missing compiled dependency symbol: {symbol}")

    outputs = files("config(//09-cross-build:answer, target)")
    archives = [path for path in outputs if path.suffix == ".a"]
    require({path.name for path in archives} == {"libanswer.a", "libtiny_math.a"},
            "Expected both the CMake and Conan static libraries")
    for archive in archives:
        machines = re.findall(r"Machine:\s+([^\n]+)", run(tools["readelf"]["path"], "-hW", archive))
        require(machines and all(machine.strip() == "AArch64" for machine in machines),
                f"Non-ARM64 or empty dependency archive: {archive}")
    cmake = json.loads(single([path for path in outputs if path.name.endswith(".manifest.json")]).read_text())
    conan_target = "config(//09-cross-build:answer_conan, target)"
    snapshot = json.loads(single([path for path in files(conan_target)
                                  if path.name.endswith(".manifest.json")]).read_text())
    for variant in (cmake["variant"], snapshot["variant"]):
        require(variant["preset"] == PRESET and variant["sanitizer"] == "none"
                and variant["environment_sha256"] == environment["environment_sha256"],
                "CMake/Conan variant does not match the cross environment")
    require(cmake["variant"]["build_type"] == mode.title(), "CMake build mode is incorrect")
    require(snapshot["private_home_removed"], "Private Conan home was not removed")
    require(snapshot["variant"]["lock_sha256"] == digest(LESSON / "conan.lock"), "Conan lock differs")
    packages = snapshot["packages"]
    require(len(packages) == 1 and packages[0]["ref"].startswith("tiny_math/1.0#")
            and packages[0]["binary"] == "Build" and packages[0]["context"] == "host"
            and packages[0]["settings"]["arch"] == "armv8"
            and packages[0]["settings"]["build_type"] == mode.title(),
            "Locked dependency was not built for the selected ARM64 mode")

    profiles = {}
    for context, arch, chain, hash_key in (
        ("host", "armv8", cross, "profile_sha256"),
        ("build", "x86_64", native, "build_profile_sha256"),
    ):
        path = single(files(f"labels({context}_profile, {conan_target})"))
        profile = configparser.ConfigParser(interpolation=None, delimiters=("=",))
        profile.read_string(path.read_text())
        require(profile["settings"]["arch"] == arch and profile["settings"]["build_type"] == mode.title(),
                f"Incorrect {context} profile settings")
        compilers = json.loads(profile["conf"]["tools.build:compiler_executables"])
        require(compilers["c"] == chain["tools"]["gcc"]["path"]
                and compilers["cpp"] == chain["tools"]["g++"]["path"],
                f"Incorrect {context} compiler selection")
        require(digest(path) == snapshot["variant"][hash_key], f"Snapshot used a different {context} profile")
        profiles[context] = {"path": str(path), "arch": arch, "compilers": compilers, "sha256": digest(path)}

    graph = json.loads(run("bazel", "aquery", *options, f'mnemonic("Cpp(Compile|Link)", deps({TARGET}))',
                           "--output=jsonproto", "--include_artifacts=false"))
    actions = graph.get("actions", [])
    require({action["mnemonic"] for action in actions} == {"CppCompile", "CppLink"},
            "Expected native-rule compile and link actions")
    for action in actions:
        require(action["arguments"][0] in (compiler, tools["g++"]["path"]),
                "Native-rule consumer used a non-cross compiler")

    print(f"PASS {mode}: ARM64 ELF/libraries, cross compiler, profiles and locked dependency; no target execution",
          flush=True)
    return {
        "mode": mode, "binary": str(binary), "binary_sha256": digest(binary),
        "elf_machine": "AArch64", "interpreter": interpreter.group(1), "runpaths": runpaths,
        "archives": [{"path": str(path), "sha256": digest(path)} for path in archives],
        "environment_manifest": str(env_path), "environment_sha256": environment["environment_sha256"],
        "compiler": compiler, "compiler_version": tools["gcc"]["version"], "compiler_execution_cpu": "x86_64",
        "target_triple": cross["target_triple"], "compiler_sysroot": cross["sysroot"],
        "builtin_includes": include_dirs, "library_search_dirs": library_dirs,
        "compiler_search_output": search_dirs, "profiles": profiles, "package": packages[0],
        "actions": [{"mnemonic": action["mnemonic"], "argv": action["arguments"]} for action in actions],
        "deployment_runtime_present": environment["sdk"]["present"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("debug", "release"), action="append")
    args = parser.parse_args()
    modes = list(dict.fromkeys(args.mode or ("debug", "release")))
    report = WORKSPACE / ".forge-evidence/09-cross-build.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    data = {"status": "RUNNING", "scope": "build-and-static-inspection", "preset": PRESET,
            "target_execution": "NOT_RUN", "deployment": "NOT_PERFORMED", "checks": []}
    report.write_text(json.dumps(data, indent=2) + "\n")
    try:
        require(platform.system() == "Linux" and platform.machine() == "x86_64",
                "This lesson requires the controlled Linux/x86_64 build container")
        before = source_snapshot()
        execution_root = Path(run("bazel", "info", "execution_root"))
        data["output_base"] = run("bazel", "info", "output_base")
        for mode in modes:
            data["checks"].append(check_mode(mode, execution_root))
        require(source_snapshot() == before, "Builds modified source inputs or locks")
        data.update(status="PASS", source_inputs_unchanged=True)
        print(f"Build-only cross example verified. No deployment or target execution. Report: {report}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, configparser.Error, subprocess.TimeoutExpired) as error:
        data.update(status="FAIL", error=str(error))
        print("FAIL " + str(error), flush=True)
        return 1
    finally:
        report.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
