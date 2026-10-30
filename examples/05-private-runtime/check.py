#!/usr/bin/env python3
"""Build the private-runtime lesson and verify its extracted layout."""

import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


WORKSPACE = Path(__file__).resolve().parents[1]
LESSON = "05-private-runtime"
PACKAGE = "forge-example-private-runtime"
LIBRARY = "libforge_private_answer.so"


def run(*args, expected=True, env=None):
    result = subprocess.run(args, cwd=WORKSPACE, env=env, text=True, capture_output=True)
    if (result.returncode == 0) != expected:
        raise RuntimeError(f"{' '.join(map(str, args))}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def find_binary(root):
    binaries = sorted((root / "opt/eros" / PACKAGE / "bin").glob("*"))
    require(len(binaries) == 1, f"Expected one installed program, got {binaries}")
    return binaries[0]


def check_mode(mode):
    run("bazel", "build", f"--config={mode}", f"//{LESSON}:runtime_tar")
    payload = WORKSPACE / f"bazel-bin/{LESSON}/runtime_tar.tar.gz"
    require(payload.is_file(), f"Missing runtime payload: {payload}")
    with tempfile.TemporaryDirectory(prefix=f"forge-{LESSON}-", dir="/tmp/kilo") as directory:
        root = Path(directory)
        with tarfile.open(payload) as archive:
            archive.extractall(root, filter="data")
        binary = find_binary(root)
        library_root = root / "opt/eros" / PACKAGE / "lib"
        require((library_root / LIBRARY).is_symlink(), "Missing unversioned library link")
        require((library_root / (LIBRARY + ".1")).is_symlink(), "Missing SONAME link")
        require((library_root / (LIBRARY + ".1.0.0")).is_file(), "Missing versioned library payload")
        resource = root / "opt/eros" / PACKAGE / "share/private-runtime.txt"
        require(resource.is_file(), "Missing installed resource")
        dynamic = run("readelf", "-d", binary).stdout
        require(f"Shared library: [{LIBRARY}.1]" in dynamic, "Program does not need the versioned library")
        require("$ORIGIN/../lib" in dynamic, "Program lacks a private relative RUNPATH")
        environment = os.environ.copy()
        environment.pop("LD_LIBRARY_PATH", None)
        environment.pop("LD_PRELOAD", None)
        result = run(binary, env=environment).stdout.strip()
        require(result == "result=41 marker=FORGE_PRIVATE_RUNTIME_MARKER layout=private",
                f"Unexpected extracted result: {result!r}")
    print(f"PASS {mode}: extracted library, SONAME links, resource and RUNPATH")


def check_bazel_run(mode):
    output = run("bazel", "run", f"--config={mode}", f"//{LESSON}:app").stdout
    require("result=41 marker=FORGE_PRIVATE_RUNTIME_MARKER layout=private" in output,
            f"Bazel run layout failed: {output!r}")


def main():
    for mode in ("debug", "release"):
        check_mode(mode)
    check_bazel_run("debug")
    print("Private runtime example verified")


if __name__ == "__main__":
    main()
