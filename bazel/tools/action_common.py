"""Controlled execution, snapshot validation, and independent debug artifacts."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_environment(path, home):
    manifest = json.loads(Path(path).read_text())
    tools = manifest["tools"]
    env = {
        "PATH": ":".join(dict.fromkeys(str(Path(t["path"]).parent) for t in tools.values())),
        "HOME": str(Path(home).resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": ":".join(manifest.get("python_path", [])),
        "SOURCE_DATE_EPOCH": "1700000000",
        "CONAN_NON_INTERACTIVE": "1",
    }
    Path(home).mkdir(parents=True, exist_ok=True)
    return manifest, env


def run(command, env, cwd=None, capture=False):
    print("Forge: " + " ".join(str(c) for c in command), flush=True)
    result = subprocess.run([str(c) for c in command], env=env, cwd=cwd,
                            stdout=subprocess.PIPE if capture else None,
                            text=True, check=True)
    return result.stdout if capture else None


def conan_command(manifest):
    return [manifest["tools"]["python"]["path"], "-s", manifest["tools"]["conan"]["path"]]


def target_tools(manifest, preset):
    tools = dict(manifest["tools"])
    context = "cross_arm64" if "_cross_arm64" in preset else "native"
    tools.update(manifest["toolchains"][context]["tools"])
    return tools


def safe_relative(path):
    p = Path(path)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError("expected a nonempty install-relative path: " + str(path))
    return p


def validate_tree(root):
    root = Path(root).resolve()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(root):
                raise ValueError("snapshot contains escaping symlink: " + str(path))
            if not path.exists():
                raise ValueError("snapshot contains broken symlink: " + str(path))


def inventory(root):
    result = []
    root = Path(root)
    validate_tree(root)
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result.append({"path": str(path.relative_to(root)), "symlink": os.readlink(path)})
        elif path.is_file():
            result.append({"path": str(path.relative_to(root)), "sha256": sha256(path),
                           "size": path.stat().st_size})
    return result


def copy_tree(source, destination):
    source, destination = Path(source).absolute(), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        output = destination / path.relative_to(source)
        if path.is_symlink():
            target = os.readlink(path)
            if not os.path.isabs(target):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.symlink_to(target)
                continue
            # Bazel materializes tree-artifact inputs as per-file absolute
            # symlinks. Materialize those transport links, not private caches.
            marker = "/bazel-out/"
            if marker not in str(path) or not target.endswith(marker + str(path).split(marker, 1)[1]):
                raise ValueError("snapshot contains escaping absolute symlink: " + str(path))
        if path.is_dir():
            output.mkdir(parents=True, exist_ok=True)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
    validate_tree(destination)


def build_id(path, tools, env):
    result = subprocess.run([tools["readelf"]["path"], "-n", str(path)], env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    match = re.search(r"Build ID: ([0-9a-f]+)", result.stdout)
    return match.group(1) if match else None


def has_debug(path, tools, env):
    result = subprocess.run([tools["objdump"]["path"], "-h", str(path)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if ".debug_info" not in result.stdout and ".zdebug_info" not in result.stdout:
        return False
    info = subprocess.run([tools["readelf"]["path"], "--debug-dump=info", "--dwarf-depth=1", str(path)], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return "Compilation Unit @" in info.stdout and not any(
        marker in info.stdout for marker in ("DW_UT_skeleton", "DW_AT_dwo_name", "DW_AT_GNU_dwo_name")
    )


def is_binary(path):
    with open(path, "rb") as stream:
        magic = stream.read(8)
    return magic.startswith(b"\x7fELF") or magic == b"!<arch>\n"


def debug_artifacts(root, debug_root, manifest_path, tools, env, enabled, variant, strip=True, tools_by_directory=None):
    root, debug_root, manifest_path = Path(root), Path(debug_root), Path(manifest_path)
    debug_root.mkdir(parents=True, exist_ok=True)
    binaries = []
    if enabled:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file() or not is_binary(path):
                continue
            relative = path.relative_to(root)
            selected_tools = (tools_by_directory or {}).get(relative.parts[0], tools)
            if not has_debug(path, selected_tools, env):
                raise ValueError("required debug information is missing: " + str(path))
            debug = debug_root / (str(relative) + ".debug")
            debug.parent.mkdir(parents=True, exist_ok=True)
            run([selected_tools["objcopy"]["path"], "--only-keep-debug", path, debug], env)
            archive = path.suffix == ".a"
            identity = build_id(path, selected_tools, env)
            if not archive:
                if not identity:
                    raise ValueError("required ELF build ID is missing: " + str(path))
                if strip:
                    path.chmod(path.stat().st_mode | 0o200)
                    run([selected_tools["strip"]["path"], "--strip-debug", path], env)
                    run([selected_tools["objcopy"]["path"], "--add-gnu-debuglink=" + str(debug.resolve()), path], env)
                if build_id(debug, selected_tools, env) != identity or build_id(path, selected_tools, env) != identity:
                    raise ValueError("debug artifact build ID mismatch: " + str(path))
                link = debug_root / ".build-id" / identity[:2] / (identity[2:] + ".debug")
                link.parent.mkdir(parents=True, exist_ok=True)
                if not link.exists():
                    link.symlink_to(os.path.relpath(debug, link.parent))
            # Static archive DWARF must survive until its objects are linked downstream.
            binaries.append({
                "binary": os.path.relpath(path, manifest_path.parent),
                "debug_file": os.path.relpath(debug, manifest_path.parent),
                "build_id": identity,
                "binary_sha256": sha256(path),
                "debug_sha256": sha256(debug),
                "archive_debug_retained_for_link": archive,
            })
    write_json(manifest_path, {"schema_version": 1, "enabled": enabled,
                               "variant": variant, "binaries": binaries})
    return binaries
