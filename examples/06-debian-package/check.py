#!/usr/bin/env python3
"""Build the Debian lesson and inspect metadata, extraction and execution."""

import os
from pathlib import Path
import platform
import subprocess
import tempfile


WORKSPACE = Path(__file__).resolve().parents[1]
LESSON = "06-debian-package"
PACKAGE = "forge-example-debian-package"


def run(*args, expected=True, env=None):
    result = subprocess.run(args, cwd=WORKSPACE, env=env, text=True, capture_output=True)
    if (result.returncode == 0) != expected:
        raise RuntimeError(f"{' '.join(map(str, args))}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def field(deb, name):
    return run("dpkg-deb", "--field", deb, name).stdout.strip()


def build(target, mode="release", flags=(), env=None):
    arguments = ["bazel", "build", f"--config={mode}", *flags, f"//{LESSON}:{target}"]
    run(*arguments, env=env)
    return WORKSPACE / f"bazel-bin/{LESSON}/{target}.deb"


def expected_architecture():
    machine = platform.machine()
    if machine in ("x86_64", "amd64"):
        return "amd64", "X86-64"
    if machine in ("aarch64", "arm64"):
        return "arm64", "AArch64"
    raise RuntimeError(f"Unsupported example host architecture: {machine}")


def check_version_precedence():
    base = dict(os.environ)
    deb = build("deb", env=dict(base, DEB_VERSION="9.9.9"), flags=("--define=DEB_VERSION=8.8.8",))
    require(field(deb, "Version") == "1.2.3", "Explicit version attribute must win over environment and define")

    deb = build("deb_default_version", env=dict(base, DEB_VERSION="2.3.4"), flags=("--define=DEB_VERSION=3.4.5",))
    require(field(deb, "Version") == "2.3.4", "Action environment must win over --define")

    clean = dict(base)
    clean.pop("DEB_VERSION", None)
    deb = build("deb_default_version", env=clean, flags=("--define=DEB_VERSION=3.4.5",))
    require(field(deb, "Version") == "3.4.5", "--define must supply the version when the environment is empty")

    deb = build("deb_default_version", env=clean)
    require(field(deb, "Version") == "0.1.0", "Missing version inputs must use the documented default")
    print("PASS version precedence: attribute > action environment > define > default")


def check_package(mode):
    deb = build("deb", mode=mode)
    architecture, machine = expected_architecture()
    require(field(deb, "Package") == PACKAGE, "Unexpected package name")
    require(field(deb, "Architecture") == architecture, "Native architecture was not selected automatically")
    contents = run("dpkg-deb", "--contents", deb).stdout
    require("bin/app" in contents and "share/debian-package.txt" in contents, "Payload is missing the program or resource")
    with tempfile.TemporaryDirectory(prefix=f"forge-{LESSON}-", dir="/tmp/kilo") as directory:
        root = Path(directory)
        run("dpkg-deb", "--extract", deb, root)
        binary = root / "opt/eros" / PACKAGE / "bin/app"
        require(binary.is_file(), "Installed program is missing")
        header = run("readelf", "-h", binary).stdout
        require(machine in header, f"ELF machine does not match {architecture}")
        environment = os.environ.copy()
        environment.pop("LD_LIBRARY_PATH", None)
        environment.pop("LD_PRELOAD", None)
        result = run(binary, env=environment).stdout.strip()
        require(result == "result=41 marker=FORGE_DEBIAN_PACKAGE_MARKER layout=private",
                f"Unexpected package execution result: {result!r}")
    print(f"PASS {mode}: deb metadata, ELF architecture, payload and extracted execution")


def main():
    check_version_precedence()
    for mode in ("debug", "release"):
        check_package(mode)
    print("Debian package example verified")


if __name__ == "__main__":
    main()
