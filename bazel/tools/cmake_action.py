"""Build, install, and validate exact CMake outputs; never invent an executable."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import tempfile

from action_common import (copy_tree, debug_artifacts, inventory, load_environment,
                           run, safe_relative, target_tools, write_json)


def build(config):
    root = Path.cwd()
    install = (root / config["output"]).absolute()
    with tempfile.TemporaryDirectory(prefix="forge-cmake-", dir=root) as work:
        work = Path(work)
        manifest, env = load_environment(config["environment"], work / "home")
        cmake = manifest["tools"]["cmake"]["path"]
        variant = {"preset": config["preset"], "environment_sha256": manifest["environment_sha256"],
                   "build_type": config["build_type"], "sanitizer": config["sanitizer"],
                   "separate_debug_info": config["separate_debug"]}
        if config.get("foreign_install"):
            copy_tree(config["foreign_install"], install)
        else:
            source = work / "source"
            source.mkdir()
            source_root = Path(config["source_root"])
            for filename in config["sources"]:
                file = Path(filename)
                try:
                    relative = file.relative_to(source_root)
                except ValueError as error:
                    raise ValueError("source must be below cmake_lists directory: " + filename) from error
                destination = source / safe_relative(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)
            flags = ["-g", "-fPIC", "-ffile-prefix-map=" + str(root) + "=.",
                     "-ffile-prefix-map=" + str(source) + "=" + str(source_root),
                     "-fdebug-prefix-map=" + str(work / "build") + "=."]
            sanitizer = config["sanitizer"]
            if sanitizer != "none":
                flags += ["-fsanitize=" + sanitizer.replace("asan", "address").replace("ubsan", "undefined").replace("tsan", "thread").replace("_", ","),
                          "-fno-omit-frame-pointer"]
            link_flags = flags + (["-static-libgcc", "-static-libstdc++"] if config["static_cpp_runtime"] else []) + config.get("linkopts", [])
            cflags = flags + config.get("copts", []) + config.get("conlyopts", [])
            cxxflags = flags + config.get("copts", []) + config.get("cxxopts", [])
            flag_variables = {
                "CMAKE_C_FLAGS": cflags,
                "CMAKE_CXX_FLAGS": cxxflags,
                "CMAKE_EXE_LINKER_FLAGS": link_flags,
                "CMAKE_SHARED_LINKER_FLAGS": link_flags,
                "CMAKE_MODULE_LINKER_FLAGS": link_flags,
            }
            cache_entries = {}
            raw_flags = {}
            for key, value in config["cache_entries"].items():
                if key in ("CMAKE_TOOLCHAIN_FILE", "CMAKE_INSTALL_PREFIX", "CMAKE_BUILD_TYPE", "CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER", "CMAKE_SYSROOT", "CMAKE_FIND_ROOT_PATH", "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY", "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE", "CMAKE_FIND_ROOT_PATH_MODE_PACKAGE", "CMAKE_STAGING_PREFIX"):
                    raise ValueError("cache entry cannot override the normalized Forge variant: " + key)
                if any(token in value for token in ("-fsanitize", "-fno-sanitize", "--sysroot", "--dynamic-linker")):
                    raise ValueError("use the canonical Forge variant instead of overriding sanitizer/SDK flags: " + key)
                if key in flag_variables:
                    raw_flags[key] = value
                else:
                    cache_entries[key] = value
            # Setting CMAKE_*_FLAGS on the command line discards the preset's
            # *_INIT flags, including the SDK loader. Compose after including
            # the preset instead; repeated try_compile loads remain idempotent.
            toolchain = work / "forge_toolchain.cmake"
            lines = ["include(" + json.dumps(str((root / config["toolchain"]).resolve())) + ")"]
            if config.get("conan_snapshot"):
                snapshot = (root / config["conan_snapshot"]).resolve()
                # It is a validated target snapshot, not an arbitrary host
                # prefix. Keep cross root-only search while making it visible.
                lines.append("list(APPEND CMAKE_FIND_ROOT_PATH " + json.dumps(str(snapshot)) + ")")
            for variable, values in flag_variables.items():
                value = shlex.join(values) + (" " + raw_flags[variable] if variable in raw_flags else "")
                value = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
                lines.append('set(' + variable + ' "${' + variable + '_INIT} ' + value + '" CACHE STRING "Forge flags" FORCE)')
            toolchain.write_text("\n".join(lines) + "\n")
            command = [cmake, "-S", str(source), "-B", str(work / "build"), "-G", "Unix Makefiles",
                       "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
                       "-DCMAKE_BUILD_TYPE=" + config["build_type"],
                       "-DCMAKE_INSTALL_PREFIX=" + str(install),
                       "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                       "-DCMAKE_BUILD_RPATH_USE_ORIGIN=ON",
                       "-DCMAKE_INSTALL_RPATH=$ORIGIN/../lib;$ORIGIN",
                       "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
            if config.get("conan_snapshot"):
                command += ["-DCMAKE_PREFIX_PATH=" + str(snapshot / "generators"),
                            "-DCMAKE_MODULE_PATH=" + str(snapshot / "generators")]
                variant["conan_manifest"] = json.loads((snapshot / "manifest.json").read_text())["variant"]
            for key, value in cache_entries.items():
                command.append("-D" + key + "=" + value)
            run(command, env)
            command = [cmake, "--build", str(work / "build"), "--parallel", str(config["jobs"])]
            if config.get("target"):
                command += ["--target", config["target"]]
            run(command, env)
            run([cmake, "--install", str(work / "build")], env)
            if config.get("conan_snapshot"):
                identities = json.loads((snapshot / "manifest.json").read_text())["package_identity"]
                for identity in identities:
                    if identity["context"] != "host":
                        continue
                    package = snapshot / "packages" / identity["name"]
                    installed_package = install / "conan" / package.name
                    copy_tree(package, installed_package)
                    # Preserve complete private shared-library SONAME chains.
                    for subdir in ("lib", "bin"):
                        directory = installed_package / subdir
                        if not directory.exists():
                            continue
                        for entry in sorted(directory.iterdir()):
                            if ".so" not in entry.name:
                                continue
                            destination = install / "lib" / entry.name
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            if destination.exists() or destination.is_symlink():
                                raise ValueError("private runtime library install collision: " + str(destination))
                            if entry.is_symlink():
                                destination.symlink_to(os.readlink(entry))
                            else:
                                shutil.copy2(entry, destination)
        for relative, output in config["declared"].items():
            source = install / safe_relative(relative)
            if not source.is_file():
                raise ValueError("declared install output is missing: " + relative)
            kind = config.get("declared_types", {}).get(relative)
            if kind:
                with source.open("rb") as stream:
                    magic = stream.read(8)
                if kind == "archive" and magic != b"!<arch>\n":
                    raise ValueError("declared static library is not an archive: " + relative)
                if kind in ("shared", "executable") and not magic.startswith(b"\x7fELF"):
                    raise ValueError("declared " + kind + " is not an ELF binary: " + relative)
                if kind == "shared":
                    dynamic = run([target_tools(manifest, config["preset"])["readelf"]["path"], "-d", source], env, capture=True)
                    soname = re.search(r"\(SONAME\).*\[([^\]]+)\]", dynamic)
                    if soname and source.name != soname.group(1):
                        raise ValueError("shared export must name its runtime SONAME: " + relative + " -> " + soname.group(1))
                if kind == "executable" and not source.stat().st_mode & 0o111:
                    raise ValueError("declared executable is not executable: " + relative)
        debug_artifacts(install, config["debug_output"], config["debug_manifest"],
                        target_tools(manifest, config["preset"]), env, config["separate_debug"], variant)
        if config["separate_debug"]:
            debug_sources = Path(config["debug_output"]) / "sources"
            for filename in config["sources"]:
                file = Path(filename)
                relative = file.relative_to(Path(config["source_root"])) if file.is_absolute() else file
                destination = debug_sources / "project" / safe_relative(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if file.is_dir():
                    copy_tree(file, destination)
                else:
                    shutil.copy2(file, destination)
            if config.get("conan_snapshot") and (snapshot / "sources").is_dir():
                copy_tree(snapshot / "sources", debug_sources / "conan")
            document = json.loads(Path(config["debug_manifest"]).read_text())
            document["sources"] = {"directory": os.path.relpath(debug_sources, Path(config["debug_manifest"]).parent),
                                   "files": inventory(debug_sources) if debug_sources.exists() else []}
            write_json(config["debug_manifest"], document)
        for relative, output in config["declared"].items():
            destination = Path(output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(install / relative, destination)
        write_json(config["manifest"], {"schema_version": 1, "variant": variant,
                                        "files": inventory(install),
                                        "declared_outputs": list(config["declared"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        build(json.loads(Path(args.config).read_text()))
    except Exception as error:
        raise SystemExit("CMake install/export failed: " + str(error)) from error
