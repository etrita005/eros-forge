"""Strict, isolated Conan installation with a relocatable declared snapshot."""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import re

from action_common import (conan_command, debug_artifacts, inventory, load_environment,
                           run, sha256, target_tools, write_json)


def install(config):
    root = Path.cwd()
    output = (root / config["output"]).absolute()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forge-conan-", dir=root) as work:
        work = Path(work)
        manifest, env = load_environment(config["environment"], work / "home")
        env["CONAN_HOME"] = str(work / "conan_home")
        identity = manifest["environment_sha256"]
        env["EROS_ENVIRONMENT_ID"] = identity
        env["EROS_CAPTURE_SOURCES"] = "1" if config["separate_debug"] else "0"
        conan = conan_command(manifest)
        run(conan + ["remote", "list"], env)
        run(conan + ["remote", "remove", "*"], env)
        if config.get("file_remote"):
            index = work / "file_remote"
            # Conan's local index export hooks may rewrite their input links.
            # Never give them a source-workspace or sandbox-input directory.
            shutil.copytree(root / config["file_remote"], index, symlinks=False)
            run(conan + ["remote", "add", "forge-files", str(index),
                         "-t", "local-recipes-index"], env)
        remotes = {}
        if config.get("remote_config"):
            remotes = json.loads(Path(config["remote_config"]).read_text())
            if "packages" not in remotes:
                raise ValueError("HTTP remotes require a packages pin list (empty means source-build only)")
            for name, url in remotes["remotes"].items():
                run(conan + ["remote", "add", name, url], env)
            for pinned in remotes["packages"]:
                reference = pinned["ref"] + ":" + pinned["package_id"] + "#" + pinned["prev"]
                run(conan + ["download", reference, "--remote=" + pinned.get("remote", next(iter(remotes["remotes"])))], env)
        for recipe in config.get("local_recipes", []):
            run(conan + ["export", str((root / recipe).resolve())], env)
        if config.get("cache_archive"):
            run(conan + ["cache", "restore", str((root / config["cache_archive"]).resolve())], env)
        host = (root / config["host_profile"]).resolve()
        if config.get("sanitizer") == "asan_ubsan":
            effective_host = work / "effective.profile"
            effective_host.write_text(re.sub(r"-fsanitize=[a-z,]+", "-fsanitize=address,undefined", host.read_text()))
            host = effective_host
        profile = work / "host.profile"
        # conf selectors are regular expressions in Conan 2, not shell globs.
        profile.write_text("include(" + str(host) + ")\n[conf]\n"
                           "user.eros:environment=" + identity + "\n"
                           "user.eros:separate_debug=" + str(config["separate_debug"]) + "\n"
                           'tools.info.package_id:confs=["user\\.eros:.*", "tools\\.build:(?!jobs$).*"]\n')
        # Conan's defines field preserves literal macro quotes through its
        # build-system generators, unlike concatenated raw compiler flags.
        defines = [flag[2:] for flag in config.get("copts", []) if flag.startswith("-D") and len(flag) > 2]
        common = [flag for flag in config.get("copts", []) if not (flag.startswith("-D") and len(flag) > 2)]
        additions = {"defines": defines, "cflags": common + config.get("conlyopts", []),
                     "cxxflags": common + config.get("cxxopts", []),
                     "exelinkflags": config.get("linkopts", []), "sharedlinkflags": config.get("linkopts", [])}
        with profile.open("a") as stream:
            for key, flags in additions.items():
                if flags:
                    stream.write("tools.build:" + key + "+=" + json.dumps(flags) + "\n")
        build_profile = work / "build.profile"
        # Build requirements run on the execution host, without target flags or
        # sanitizers, but need the same verified environment identity contract.
        build_profile.write_text("include(" + str((root / config["build_profile"]).resolve()) + ")\n[conf]\n"
                                 "user.eros:environment=" + identity + "\n"
                                 "user.eros:separate_debug=" + str(config["separate_debug"]) + "\n"
                                 'tools.info.package_id:confs=["user\\.eros:.*", "tools\\.build:(?!jobs$).*"]\n')
        consumer = work / "consumer"
        consumer.mkdir()
        conanfile = Path(config["conanfile"])
        for file in [conanfile] + [Path(p) for p in config.get("extra_srcs", [])]:
            if not file.is_relative_to(conanfile.parent):
                continue
            destination = consumer / file.relative_to(conanfile.parent)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / file, destination)
        command = conan + ["install", str(consumer / conanfile.name),
                           "--profile:host=" + str(profile),
                           "--profile:build=" + str(build_profile),
                           "--lockfile=" + str((root / config["lockfile"]).resolve()),
                           "--build=missing", "--format=json", "-g", "CMakeDeps",
                           "--output-folder=" + str(output / "generators"),
                           "--deployer=" + str((root / config["deployer"]).resolve()),
                           "--deployer-folder=" + str(output),
                           "-c", "tools.build:jobs=" + str(config["jobs"])]
        graph = json.loads(run(command, env, capture=True))
        nodes = graph["graph"]["nodes"].values()
        packages = []
        for node in nodes:
            if not node.get("package_id") or not node.get("ref"):
                continue
            packages.append({key: node.get(key) for key in (
                "ref", "rrev", "package_id", "prev", "binary", "remote", "package_type",
                "settings", "options", "context")})
        deployed = json.loads((output / "deployed.json").read_text())
        replacements = {p["original_package_folder"]: "${_EROS_SNAPSHOT_ROOT}/packages/" + p["name"]
                        for p in deployed}
        replacements[str(output)] = "${_EROS_SNAPSHOT_ROOT}"
        for path in output.rglob("*"):
            if path.is_relative_to(output / "sources"):
                continue
            if path.is_file():
                if path.suffix != ".cmake":
                    if path.is_relative_to(output / "generators"):
                        path.unlink()
                    elif path.suffix == ".pc":
                        text = path.read_text()
                        prefix = "${pcfiledir}/" + os.path.relpath(output, path.parent)
                        for source, destination in replacements.items():
                            text = text.replace(source, destination.replace("${_EROS_SNAPSHOT_ROOT}", prefix))
                        if str(work) in text:
                            raise ValueError("pkg-config metadata retains private Conan path: " + str(path))
                        path.write_text(text)
                    continue
                text = path.read_text()
                for source, destination in replacements.items():
                    text = text.replace(source, destination)
                if str(work) in text or "conan_home" in text:
                    raise ValueError("CMake metadata retains private Conan path: " + str(path))
                relative_root = os.path.relpath(output, path.parent)
                path.write_text('get_filename_component(_EROS_SNAPSHOT_ROOT "${CMAKE_CURRENT_LIST_DIR}/' + relative_root + '" ABSOLUTE)\n' + text)
        for p in deployed:
            p.pop("original_package_folder")
        (output / "deployed.json").unlink()
        for pinned in remotes.get("packages", []):
            candidates = [p for p in packages if p["ref"] == pinned["ref"] and
                          p["package_id"] == pinned["package_id"] and p["prev"] == pinned["prev"]]
            if not candidates:
                raise ValueError("remote selected an unpinned package revision: " + pinned["ref"])
            actual_files = {f["path"]: f["sha256"] for f in inventory(output / "packages" / pinned["name"]) if "sha256" in f}
            if set(actual_files) != set(pinned["files"]):
                raise ValueError("binary identity lock must hash every package file: " + pinned["ref"])
            for relative, digest in pinned["files"].items():
                if sha256(output / "packages" / pinned["name"] / relative) != digest:
                    raise ValueError("precompiled binary file hash mismatch: " + relative)
        for package in packages:
            if package["binary"] == "Download" and not any(
                pinned["ref"] == package["ref"] and pinned["package_id"] == package["package_id"] and pinned["prev"] == package["prev"]
                for pinned in remotes.get("packages", [])
            ):
                raise ValueError("refusing unpinned remote binary: " + package["ref"])
        variant = {"preset": config["preset"], "sanitizer": config["sanitizer"],
                   "environment_sha256": identity, "lock_sha256": sha256(config["lockfile"]),
                   "profile_sha256": sha256(config["host_profile"]),
                   "build_profile_sha256": sha256(config["build_profile"]),
                   "separate_debug_info": config["separate_debug"]}
        # Required symbols are validated even for downloaded binaries. Static archive
        # DWARF is retained so downstream CMake/native final links can consume it.
        debug_artifacts(output / "packages", config["debug_output"], config["debug_manifest"],
                        target_tools(manifest, config["preset"]), env, config["separate_debug"], variant, strip=False,
                        tools_by_directory={p["name"]: manifest["tools"] for p in deployed if p["context"] == "build"})
        if (output / "sources").is_dir():
            debug_sources = Path(config["debug_output"]) / "sources" / "conan"
            shutil.copytree(output / "sources", debug_sources, symlinks=True)
            debug_document = json.loads(Path(config["debug_manifest"]).read_text())
            debug_document["sources"] = {"directory": os.path.relpath(debug_sources, Path(config["debug_manifest"]).parent),
                                         "files": inventory(debug_sources)}
            write_json(config["debug_manifest"], debug_document)
        result = {"schema_version": 1, "variant": variant, "packages": packages,
                  "package_identity": deployed, "files": inventory(output),
                  "pinned_binary_downloads": [p["ref"] + ":" + p["package_id"] + "#" + p["prev"] for p in remotes.get("packages", [])],
                  "private_home_removed": True}
        # The context manager removes CONAN_HOME before the success manifest is written.
    if Path(env["CONAN_HOME"]).exists():
        raise ValueError("private Conan home survived the snapshot boundary")
    write_json(config["manifest"], result)
    (output / "manifest.json").write_text(Path(config["manifest"]).read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        install(json.loads(Path(args.config).read_text()))
    except Exception as error:
        raise SystemExit("Conan snapshot failed: " + str(error)) from error
