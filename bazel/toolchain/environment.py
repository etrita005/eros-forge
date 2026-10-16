#!/usr/bin/env python3
"""Capture and validate the installed controlled environment, without a Conan home."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import pprint
import re
import shutil
import stat
import subprocess
import sys
import sysconfig

_HASHES = {}
_ENV = {
    "PATH": "/usr/bin:/bin:/usr/local/bin", "LC_ALL": "C", "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    "HOME": str(Path.cwd() / ".forge-probe-home"),
    "CONAN_HOME": str(Path.cwd() / ".forge-probe-conan"),
}
_RUNTIMES = [
    "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
    "libstdc++.so.6", "libgcc_s.so.1", "libatomic.so.1", "libutil.so.1",
    "libresolv.so.2", "libasan.so", "libubsan.so", "libtsan.so",
    "ld-linux-aarch64.so.1", "ld-linux-x86-64.so.2",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run(argv, env=None):
    result = subprocess.run(argv, text=True, capture_output=True, env=env or _ENV, timeout=120)
    if result.returncode:
        raise ValueError("environment command failed: " + repr(argv) + "\n" + result.stdout + result.stderr)
    return result.stdout.strip(), result.stderr.strip()


def file_identity(path):
    path = Path(path)
    if not path.exists():
        if path.is_symlink():
            target = os.readlink(path)
            return {"path": str(path), "kind": "broken_symlink", "sha256": digest(target), "link_target": target}
        return {"path": str(path), "kind": "missing", "sha256": None}
    info = path.stat()
    resolved = str(path.resolve())
    key = (resolved, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if key not in _HASHES:
        with path.open("rb") as stream:
            _HASHES[key] = hashlib.file_digest(stream, "sha256").hexdigest()
    record = {"path": str(path), "kind": "symlink" if path.is_symlink() else "file", "sha256": _HASHES[key], "mode": stat.S_IMODE(info.st_mode)}
    if path.is_symlink():
        record["link_target"] = os.readlink(path)
    return record


def tree_files(root):
    root = Path(root)
    result = []
    seen = set()
    for directory, dirs, files in os.walk(root, followlinks=True):
        for name in sorted(dirs):
            path = Path(directory) / name
            if path.is_symlink():
                target = os.readlink(path)
                result.append({"path": str(path), "kind": "directory_symlink", "sha256": digest(target), "link_target": target})
        resolved = str(Path(directory).resolve())
        if resolved in seen:
            dirs[:] = []
            continue
        seen.add(resolved)
        dirs.sort()
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_file() or path.is_symlink():
                result.append(file_identity(path))
    return result


def tree_identity(root):
    root = Path(root)
    if not root.exists():
        return {"path": str(root), "kind": "missing", "sha256": None}, []
    files = tree_files(root)
    relative = [dict(entry, path=str(Path(entry["path"]).relative_to(root))) for entry in files]
    record = {"path": str(root), "kind": "tree", "sha256": digest(relative), "files": relative}
    if root.is_symlink():
        record["link_target"] = os.readlink(root)
    return record, [entry["path"] for entry in files if Path(entry["path"]).is_file()]


def executable(name, path, args=None, env=None):
    if not path or not Path(path).is_file():
        raise ValueError("required controlled tool is missing: " + name + " (" + str(path) + ")")
    stdout, stderr = run([str(path)] + (args or ["--version"]), env)
    output = stdout or stderr
    first = output.splitlines()[0]
    versions = re.findall(r"\d+(?:\.\d+)+", first)
    result = file_identity(path)
    result.update(version=versions[-1] if versions else first, version_output=first)
    return result


def toolchain(spec, prefix):
    tools = {}
    for name in spec["tool_names"]:
        suffix = "-" + spec["gcc_major"] if name in ["gcc", "g++", "cpp", "gcov"] else ""
        path = "/usr/bin/" + prefix + name + suffix
        tools[name] = executable(name, path, ["-dumpfullversion", "-dumpversion"] if name in ["gcc", "g++"] else None)
    compiler = tools["gcc"]["path"]
    triple, _ = run([compiler, "-dumpmachine"])
    sysroot, _ = run([compiler, "-print-sysroot"])
    _, includes = run([tools["g++"]["path"], "-E", "-x", "c++", "-v", "/dev/null"])
    builtin_includes = []
    collecting = False
    for line in includes.splitlines():
        if "#include <...> search starts here:" in line:
            collecting = True
        elif "End of search list." in line:
            collecting = False
        elif collecting:
            builtin_includes.append(str(Path(line.strip()).resolve()))
    search, _ = run([compiler, "-print-search-dirs"])
    libraries = next(line.split("=", 1)[1] for line in search.splitlines() if line.startswith("libraries:"))
    library_dirs = sorted({str(Path(p).resolve()) for p in libraries.split(":") if Path(p).is_dir()})
    support = set(builtin_includes)
    for name in ["cc1", "cc1plus", "collect2", "lto1", "lto-wrapper"]:
        path, _ = run([compiler, "-print-prog-name=" + name])
        if Path(path).is_file():
            support.add(str(Path(path).resolve().parent))
    libgcc, _ = run([compiler, "-print-libgcc-file-name"])
    support.add(str(Path(libgcc).parent))
    for path in ["/usr/lib/" + triple, "/usr/" + triple + "/lib", "/usr/" + triple + "/include"]:
        if Path(path).is_dir():
            support.add(path)
    runtimes = []
    sonames = []
    for name in _RUNTIMES:
        path, _ = run([compiler, "-print-file-name=" + name])
        if not Path(path).is_file():
            continue
        entry = file_identity(str(Path(path).resolve()))
        output, _ = run([tools["readelf"]["path"], "-d", path])
        match = re.search(r"\(SONAME\).*\[(.+?)\]", output)
        soname = match.group(1) if match else Path(path).name
        entry["soname"] = soname
        runtimes.append(entry)
        sonames.append(soname)
    return {
        "tools": tools, "target_triple": triple, "sysroot": sysroot,
        "builtin_includes": builtin_includes, "library_search_dirs": library_dirs,
        "support_roots": sorted(support), "runtime_files": runtimes,
        "runtime_sonames": sorted(set(sonames)),
    }


def python_paths(conan):
    candidates = [Path(conan).parent.parent / "lib" / ("python" + sysconfig.get_python_version()) / "site-packages"]
    candidates += [Path(p) for p in sys.path if "site-packages" in p or "dist-packages" in p]
    return sorted({str(path.resolve()) for path in candidates if path.is_dir()})


def shared_libraries(path):
    result = subprocess.run(["/usr/bin/ldd", path], text=True, capture_output=True, env=_ENV)
    if result.returncode:
        return []  # Python entry scripts and static executables do not have ELF deps.
    return sorted(set(re.findall(r"(?:=>\s*|^\s*)(/[^\s()]+)", result.stdout, re.MULTILINE)))


def check_versions(manifest):
    expected = manifest["expected_versions"]
    for name in ["bazel", "cmake", "conan"]:
        actual = manifest["tools"][name]["version"]
        if actual != expected[name]:
            raise ValueError("controlled " + name + " version mismatch: expected " + expected[name] + ", found " + actual)
    if manifest["tools"]["python"]["version"].split(".")[0] != expected["python_major"]:
        raise ValueError("controlled Python major version mismatch")
    for key, cfg in manifest["toolchains"].items():
        for name in ["gcc", "g++"]:
            if cfg["tools"][name]["version"].split(".")[0] != manifest["gcc_major"]:
                raise ValueError(key + ": expected GCC " + manifest["gcc_major"] + ", found " + cfg["tools"][name]["version"])
        if key == "native" and cfg["target_triple"] != manifest["host"]["target_triple"]:
            raise ValueError("native GCC target does not match the execution host")
        if key == "cross_arm64" and cfg["target_triple"] != "aarch64-linux-gnu":
            raise ValueError("ARM64 compiler has incorrect target triple: " + cfg["target_triple"])


def check_sdk(manifest):
    sdk = manifest["sdk"]
    if not sdk["present"]:
        return
    root = Path(sdk["path"], "lib")
    for runtime in manifest["toolchains"]["cross_arm64"]["runtime_files"]:
        path = root / runtime["soname"]
        if not path.is_file() or file_identity(path)["sha256"] != runtime["sha256"]:
            raise ValueError("SDK/runtime identity mismatch: " + str(path) + " does not match the controlled ARM64 compiler runtime " + runtime["path"])


def capture(spec, conan, bazel):
    cpu = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}.get(platform.machine().lower())
    if platform.system() != "Linux" or cpu is None:
        raise ValueError("Forge requires a supported ARM64 or x86_64 Linux execution host")
    triple = ("aarch64" if cpu == "arm64" else "x86_64") + "-linux-gnu"
    chains = {"native": toolchain(spec, ""), "cross_arm64": toolchain(spec, "aarch64-linux-gnu-")}
    conan = conan or shutil.which("conan", path=_ENV["PATH"])
    if not conan:
        raise ValueError("controlled Conan executable not found; pass its installed path with --conan")
    paths = python_paths(conan)
    python_env = dict(_ENV, PYTHONPATH=os.pathsep.join(paths))
    tools = dict(chains["native"]["tools"])
    common_tools = {"python": sys.executable, "bazel": bazel or shutil.which("bazel", path=_ENV["PATH"])}
    for name in ["cmake", "make", "m4", "bash"]:
        common_tools[name] = shutil.which(name, path=_ENV["PATH"])
    for name, path in common_tools.items():
        tools[name] = executable(name, path)
    conan_output, _ = run([sys.executable, "-s", conan, "--version"], python_env)
    tools["conan"] = dict(file_identity(conan), version=re.findall(r"\d+(?:\.\d+)+", conan_output)[-1], version_output=conan_output)
    manifest = {
        "schema_version": 1, "host": {"os": "linux", "cpu": cpu, "target_triple": triple},
        "expected_versions": spec["expected_versions"], "gcc_major": spec["gcc_major"],
        "supported_presets": [name for name, cfg in spec["presets"].items() if cfg["host_cpu"] == cpu],
        "tools": tools, "toolchains": chains, "python_path": paths,
    }
    check_versions(manifest)
    identities = {}
    groups = {"common": set(), "native": set(), "cross_arm64": set()}

    def add(path, group, tree=False):
        path = str(Path(path).absolute())
        if tree:
            record, files = tree_identity(path)
        else:
            record, files = file_identity(path), [path]
        identities[path] = record
        groups[group].update(files)

    # Identity and real inputs cover support programs, target headers/libraries,
    # Python/Conan installation, and CMake modules, not just entry-point scripts.
    for group, cfg in chains.items():
        for tool in cfg["tools"].values():
            add(tool["path"], group)
        for root in cfg["support_roots"]:
            add(root, group, tree=True)
    for name in ["python", "cmake", "make", "m4", "bash", "bazel", "conan"]:
        add(tools[name]["path"], "common")
    roots = set(paths + [sysconfig.get_paths()["stdlib"]])
    roots.add(str(Path(tools["cmake"]["path"]).resolve().parent.parent / "share" / ("cmake-" + ".".join(tools["cmake"]["version"].split(".")[:2]))))
    for root in sorted(roots):
        if Path(root).is_dir():
            add(root, "common", tree=True)
    # Compiler support programs themselves also depend on system shared objects.
    executables = [entry["path"] for entry in tools.values()]
    for cfg in chains.values():
        executables += [entry["path"] for entry in cfg["tools"].values()]
        for root in cfg["support_roots"]:
            executables += [str(Path(root) / name) for name in ["cc1", "cc1plus", "collect2", "lto1", "lto-wrapper"] if (Path(root) / name).is_file()]
    for path in sorted(set(executables)):
        for library in shared_libraries(path):
            add(library, "common")
    sdk, sdk_files = tree_identity(spec["sdk_path"])
    identities[spec["sdk_path"]] = sdk
    groups["cross_arm64"].update(sdk_files)
    present = sdk["kind"] != "missing"
    runtime_files = [file_identity(path) for path in sdk_files if "/lib/" in path]
    runtime_sonames = []
    for path in sdk_files:
        if "/lib/" in path and (".so" in Path(path).name):
            runtime_sonames.append(Path(path).name)
    manifest["sdk"] = {
        "path": spec["sdk_path"], "present": present, "id": sdk["sha256"] if present else "missing:" + spec["sdk_path"],
        "dynamic_interpreter": spec["sdk_path"] + "/lib/ld-linux-aarch64.so.1",
        "runtime_identity_verified": present and Path(spec["sdk_path"], "lib/ld-linux-aarch64.so.1").is_file(),
        "runtime_files": runtime_files, "runtime_sonames": sorted(set(runtime_sonames)),
    }
    manifest["identities"] = [identities[path] for path in sorted(identities)]
    check_sdk(manifest)
    manifest["environment_sha256"] = digest(manifest)
    return manifest, groups


def materialize(repository, manifest, groups):
    repository = Path(repository)
    inputs = repository / "inputs"
    inputs.mkdir(exist_ok=True)
    all_paths = sorted(set().union(*groups.values()))
    labels = {}
    for index, path in enumerate(all_paths):
        if not Path(path).is_file():
            continue
        label = "inputs/" + str(index)
        link = repository / label
        if link.is_symlink():
            link.unlink()
        link.symlink_to(path)
        labels[path] = label
    build = 'package(default_visibility = ["//visibility:public"])\n\nexports_files(["env_manifest.json", "tools.bzl"])\n'
    build += 'filegroup(name = "env_manifest", srcs = ["env_manifest.json"])\n'
    for name, paths in [("native_all", groups["common"] | groups["native"]), ("cross_arm64_all", groups["common"] | groups["cross_arm64"]), ("all_tools", set(all_paths))]:
        srcs = ["env_manifest.json"] + [labels[path] for path in sorted(paths) if path in labels]
        build += "filegroup(name = " + repr(name) + ", srcs = " + pprint.pformat(srcs, width=100) + ")\n"
    build += 'filegroup(name = "conan_tool", srcs = [' + repr(labels[manifest["tools"]["conan"]["path"]]) + '])\n'
    (repository / "BUILD.bazel").write_text(build)
    data = {
        name: dict(cfg, tools={key: value["path"] for key, value in cfg["tools"].items()})
        for name, cfg in manifest["toolchains"].items()
    }
    host_tools = {name: record["path"] for name, record in manifest["tools"].items()}
    (repository / "tools.bzl").write_text("# Generated installed tool identity.\nHOST_CPU = " + repr(manifest["host"]["cpu"]) + "\nTOOLCHAINS = " + pprint.pformat(data, width=100, sort_dicts=False) + "\nHOST_TOOLS = " + pprint.pformat(host_tools, width=100, sort_dicts=False) + "\nPYTHON = " + repr(manifest["tools"]["python"]["path"]) + "\n")


def validate(manifest, spec=None):
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported environment manifest schema")
    contents = dict(manifest)
    claimed = contents.pop("environment_sha256")
    if digest(contents) != claimed:
        raise ValueError("environment manifest digest mismatch")
    if spec is not None and (manifest["expected_versions"] != spec["expected_versions"] or manifest["gcc_major"] != spec["gcc_major"]):
        raise ValueError("environment manifest does not match the committed version policy")
    check_versions(manifest)
    check_sdk(manifest)
    for expected in manifest["identities"]:
        if expected["kind"] == "tree":
            actual, _ = tree_identity(expected["path"])
        else:
            actual = file_identity(expected["path"])
        if actual != expected:
            raise ValueError("installed environment identity mismatch: " + expected["path"] + "; regenerate only after reviewing an intentional environment upgrade")
    env = dict(_ENV, PYTHONPATH=os.pathsep.join(manifest["python_path"]))
    for name in ["bazel", "cmake", "python", "make", "m4", "bash"]:
        expected = manifest["tools"][name]
        if executable(name, expected["path"])["version"] != expected["version"]:
            raise ValueError("installed tool version differs from manifest: " + name)
    conan, _ = run([manifest["tools"]["python"]["path"], "-s", manifest["tools"]["conan"]["path"], "--version"], env)
    if re.findall(r"\d+(?:\.\d+)+", conan)[-1] != manifest["tools"]["conan"]["version"]:
        raise ValueError("installed Conan version differs from manifest")
    if not manifest["sdk"]["present"]:
        print("Forge SDK /opt/eros is missing: cross linking is available, but SDK/runtime identity and target execution are BLOCKED.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--spec", required=True)
    capture_parser.add_argument("--repository", required=True)
    capture_parser.add_argument("--conan")
    capture_parser.add_argument("--bazel")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", required=True)
    validate_parser.add_argument("--spec", default=str(Path(__file__).with_name("environment_spec.json")))
    validate_parser.add_argument("--stamp")
    args = parser.parse_args()
    try:
        if args.operation == "capture":
            spec = json.loads(Path(args.spec).read_text())
            manifest, groups = capture(spec, args.conan, args.bazel)
            materialize(args.repository, manifest, groups)
            Path(args.repository, "env_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            print("Captured Forge environment " + manifest["environment_sha256"])
        else:
            manifest = json.loads(Path(args.manifest).read_text())
            validate(manifest, json.loads(Path(args.spec).read_text()))
            if args.stamp:
                Path(args.stamp).write_text(manifest["environment_sha256"] + "\n")
            print("Validated Forge environment " + manifest["environment_sha256"])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, "Forge environment validation failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
