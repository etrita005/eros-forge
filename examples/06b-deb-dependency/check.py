#!/usr/bin/env python3
"""Build and inspect the two-deb example in the shared native workspace."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


WORKSPACE = Path(__file__).resolve().parents[1]
PACKAGE = WORKSPACE / "bazel-bin/06b-deb-dependency"


def run(*args, expected=0, env=None, diagnostic=""):
    result = subprocess.run(args, cwd=WORKSPACE, env=env, text=True, capture_output=True)
    if (result.returncode == 0) != (expected == 0):
        raise RuntimeError(f"{' '.join(map(str, args))}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    if diagnostic and diagnostic not in result.stderr:
        raise RuntimeError(f"{' '.join(map(str, args))}: missing {diagnostic!r}\n{result.stdout}{result.stderr}")
    return result.stdout


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    run("bazel", "build", "--config=release", "//06b-deb-dependency/a:a_deb", "//06b-deb-dependency/b:b_deb")
    a_deb, b_deb = PACKAGE / "a/a_deb.deb", PACKAGE / "b/b_deb.deb"
    a_name = run("dpkg-deb", "--field", a_deb, "Package").strip()
    a_version = run("dpkg-deb", "--field", a_deb, "Version").strip()
    require(run("dpkg-deb", "--field", b_deb, "Depends").strip() == f"{a_name} (= {a_version})",
            "B.deb dependency does not match the selected A.deb")
    a_files = run("dpkg-deb", "--contents", a_deb)
    b_files = run("dpkg-deb", "--contents", b_deb)
    require("libforge_example_a.so.1.0" in a_files and "libforge_example_a.so" not in b_files,
            "A's shared library must belong only to A.deb")

    with tempfile.TemporaryDirectory(prefix="forge-deb-dependency-", dir="/tmp/kilo") as directory:
        root = Path(directory)
        run("dpkg-deb", "--extract", b_deb, root)
        binary = root / "opt/eros/forge-example-b/bin/example-b"
        runtime_manifest = json.loads((binary.parent.parent / "runtime_manifest.json").read_text())
        require(runtime_manifest["external_packages"][0]["version"] == a_version
                and not any("libforge_example_a.so" in item["path"] for item in runtime_manifest["files"]),
                "B runtime manifest must describe the external A library instead of a bundled copy")
        dynamic = run("readelf", "-d", binary)
        require("libforge_example_a.so.1" in dynamic and "$ORIGIN/../../forge-example-a/lib" in dynamic,
                "B must link to A's SONAME and look in A's installed library directory")
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        run(binary, expected=1, env=env, diagnostic="libforge_example_a.so.1")
        run("dpkg-deb", "--extract", a_deb, root)
        require(run(binary, env=env).strip() == "result=41", "B did not execute A's implementation")
        shutil.rmtree(root / "opt/eros/forge-example-a")
        run(binary, expected=1, env=env, diagnostic="libforge_example_a.so.1")

    with tempfile.TemporaryDirectory(prefix="forge-deb-install-", dir="/tmp/kilo") as directory:
        root = Path(directory)
        database = root / "var/lib/dpkg"
        database.mkdir(parents=True)
        (database / "status").write_text("")
        dpkg = ("dpkg", "--root=" + str(root), "--force-not-root")
        run(*dpkg, "--install", b_deb, expected=1, diagnostic="forge-example-a")
        run(*dpkg, "--install", a_deb)
        run(*dpkg, "--configure", "forge-example-b")
        require(run(root / "opt/eros/forge-example-b/bin/example-b", env=env).strip() == "result=41",
                "B does not run after installing both debs")
        run(*dpkg, "--remove", "forge-example-a", expected=1, diagnostic="forge-example-b")
    print("B requires A: Depends, ELF, disjoint deb contents, runtime and isolated dpkg checks verified")


if __name__ == "__main__":
    main()
