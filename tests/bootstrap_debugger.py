#!/usr/bin/env python3
"""Extract Ubuntu's GDB and missing runtime packages without installing them."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess


def run(arguments, **kwargs):
    print("$ " + shlex.join(map(str, arguments)), flush=True)
    return subprocess.run(arguments, text=True, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/kilo/forge-gdb"))
    args = parser.parse_args()
    machine = platform.machine()
    if machine in ("aarch64", "arm64"):
        triple, loader = "aarch64-linux-gnu", "/lib/ld-linux-aarch64.so.1"
    elif machine in ("x86_64", "amd64"):
        triple, loader = "x86_64-linux-gnu", "/lib64/ld-linux-x86-64.so.2"
    else:
        parser.error("Only the controlled Ubuntu x86_64/ARM64 test hosts are supported")
    output = args.output.resolve()
    packages, root = output / "packages", output / "root"
    packages.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=True)
    pending, selected = ["gdb"], {}
    while pending:
        package = pending.pop()
        if package in selected:
            continue
        status = subprocess.run(["dpkg-query", "-W", "-f=${Status}", package], text=True, capture_output=True)
        if package != "gdb" and status.stdout.strip() == "install ok installed":
            continue
        policy = run(["apt-cache", "policy", package], capture_output=True).stdout
        candidate = re.search(r"Candidate:\s*(\S+)", policy)
        if not candidate or candidate.group(1) == "(none)":
            parser.error("No Ubuntu candidate for required test package: " + package)
        selected[package] = candidate.group(1)
        dependencies = run(["apt-cache", "depends", "--important", package], capture_output=True).stdout
        pending.extend(re.findall(r"^\s*Depends:\s+([a-z0-9][a-z0-9+.-]+)\s*$", dependencies, re.MULTILINE))
    for package, version in sorted(selected.items()):
        run(["apt-get", "download", package + "=" + version], cwd=packages)
    archives = sorted(packages.glob("*.deb"))
    for archive in archives:
        run(["dpkg-deb", "--extract", archive, root])
    wrapper = output / "gdb"
    wrapper.write_text(
        "#!/bin/sh\nset -eu\nexec " + shlex.join([
            loader, "--library-path", str(root / "usr/lib" / triple), str(root / "usr/bin/gdb"),
            "--data-directory=" + str(root / "usr/share/gdb"), "-iex", "set debuginfod enabled off",
        ]) + ' "$@"\n'
    )
    wrapper.chmod(0o755)
    version = run([wrapper, "--version"], capture_output=True).stdout
    (output / "bootstrap_manifest.json").write_text(json.dumps({
        "packages": selected, "gdb_version": version.splitlines()[0],
        "archives": {archive.name: hashlib.sha256(archive.read_bytes()).hexdigest() for archive in archives},
    }, indent=2) + "\n")
    print("Isolated debugger: " + str(wrapper))


if __name__ == "__main__":
    main()
