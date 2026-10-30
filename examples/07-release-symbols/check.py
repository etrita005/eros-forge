#!/usr/bin/env python3
"""Verify Release symbols, build identity and GDB source lookup."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile


WORKSPACE = Path(__file__).resolve().parents[1]
LESSON = "07-release-symbols"
PACKAGE = "forge-example-release-symbols"


def run(*args, expected=True, env=None):
    result = subprocess.run(args, cwd=WORKSPACE, env=env, text=True, capture_output=True)
    if (result.returncode == 0) != expected:
        raise RuntimeError(f"{' '.join(map(str, args))}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run("bazel", "build", "--config=release", f"//{LESSON}:app", f"//{LESSON}:symbols")
    binary = WORKSPACE / f"bazel-bin/{LESSON}/app"
    payload = WORKSPACE / f"bazel-bin/{LESSON}/symbols.tar.gz"
    require(binary.is_file() and payload.is_file(), "Missing Release binary or symbol payload")
    environment = os.environ.copy()
    environment.pop("LD_LIBRARY_PATH", None)
    environment.pop("LD_PRELOAD", None)
    result = run(binary, env=environment).stdout.strip()
    require(result == "result=41", f"Release program failed: {result!r}")

    with tempfile.TemporaryDirectory(prefix=f"forge-{LESSON}-", dir="/tmp/kilo") as directory:
        root = Path(directory)
        with tarfile.open(payload) as archive:
            archive.extractall(root, filter="data")
        manifest_path = root / "opt/eros" / PACKAGE / "debug_manifest.json"
        require(manifest_path.is_file(), "Symbol payload lacks debug_manifest.json")
        manifest = json.loads(manifest_path.read_text())
        require(manifest.get("symbols_only") is True and manifest.get("requires_matching_payload") is True,
                "Symbol payload does not declare its matching-payload contract")
        require(manifest.get("enabled") is True, "Release symbols were not enabled")
        records = manifest.get("binaries", [])
        require(len(records) == 1, f"Expected one symbol record, got {records}")
        record = records[0]
        debug_file = root / "opt/eros" / PACKAGE / record["debug_file"]
        require(debug_file.is_file(), "Declared .debug file is missing")
        require(digest(binary) == record["binary_sha256"], "Symbol record does not match the published binary")
        require(digest(debug_file) == record["debug_sha256"], "Symbol record does not match the .debug file")

        binary_notes = run("readelf", "-n", binary).stdout
        debug_notes = run("readelf", "-n", debug_file).stdout
        require(record["build_id"] in binary_notes and record["build_id"] in debug_notes,
                "Binary and symbol build IDs do not agree")
        binary_sections = run("readelf", "-S", binary).stdout
        debug_sections = run("readelf", "-S", debug_file).stdout
        require(".debug_info" not in binary_sections and ".gnu_debuglink" in binary_sections,
                "Published binary must be stripped and retain a debug link")
        require(".debug_info" in debug_sections, "Separate symbol file has no DWARF")

        result = run(
            "gdb", "-nx", "-batch",
            "-ex", "set debuginfod enabled off",
            "-ex", "set debug-file-directory " + str(debug_file.parent),
            "-ex", "file " + str(binary),
            "-ex", "break forge_release_symbol",
            "-ex", "info line forge_release_symbol",
        )
        output = result.stdout
        require(re.search(r"Breakpoint \d+ at 0x[0-9a-f]+", output), f"GDB did not resolve the breakpoint: {output}")
        require(re.search(r"07-release-symbols/main\.cc", output) and re.search(r"[Ll]ine \d+", output),
                f"GDB did not resolve the source line: {output}")
        print("PASS Release binary, separate DWARF, build identity and GDB source breakpoint")


if __name__ == "__main__":
    main()
