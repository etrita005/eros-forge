#!/usr/bin/env python3
# Copyright (c) 2024 EROS Project
#
# Generates tests/test_config_data.json from the SAME toolchain table that
# generates cc_toolchain_config / Conan profiles / CMake toolchain files
# (bazel/toolchain/generate_files.py). This is the single source of truth for
# the test framework, eliminating the per-script hardcoded ARCH_MAP /
# COMPILER_MAP / DYNAMIC_LINKER_MAP / RPATH_MAP / READELF_MAP / NM_MAP /
# OBJDUMP_MAP tables that previously drifted out of sync with the toolchain.
#
# Re-run after editing generate_files.py:
#   python3 tests/gen_test_config.py

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORGE_ROOT = os.path.dirname(HERE)
GEN_DIR = os.path.join(FORGE_ROOT, "bazel", "toolchain")

sys.path.insert(0, GEN_DIR)
from generate_files import (  # noqa: E402
    CONFIGS,
    TOOL_BIN_DIR,
    DEFAULT_SYSROOT,
)

# Native (host) dynamic linker paths. Cross configs derive theirs from the
# sysroot + dynamic_linker basename in the toolchain table; native configs have
# an empty dynamic_linker field, so the standard system path is provided here.
NATIVE_LINKER = {
    "x86_64": "/lib64/ld-linux-x86-64.so.2",
    "aarch64": "/lib/ld-linux-aarch64.so.1",
}

# `file(1)` prints these architecture tokens.
FILE_ARCH = {
    "x86_64": "x86-64",
    "aarch64": "ARM aarch64",
}


def tool(prefix, basename):
    return "{}/{}{}".format(TOOL_BIN_DIR, prefix, basename)


def build():
    data = {}
    for key, cfg in CONFIGS.items():
        cpu = cfg["cpu"]
        prefix = cfg["compiler_prefix"]
        is_cross = cfg["is_cross"]

        if is_cross:
            dynamic_linker = "{}/lib/{}".format(cfg["sysroot"], cfg["dynamic_linker"])
            rpath = "{}/lib".format(cfg["sysroot"])
        else:
            dynamic_linker = NATIVE_LINKER[cpu]
            rpath = ""

        data[key] = {
            "cpu": cpu,
            "file_arch": FILE_ARCH[cpu],
            "is_cross": is_cross,
            "compiler": tool(prefix, "g++"),
            "compiler_c": tool(prefix, "gcc"),
            "dynamic_linker": dynamic_linker,
            "rpath": rpath,
            "readelf": tool(prefix, "readelf") if prefix else "readelf",
            "nm": tool(prefix, "nm") if prefix else "nm",
            "objdump": tool(prefix, "objdump") if prefix else "objdump",
            "strip": tool(prefix, "strip") if prefix else "strip",
        }
    return data


def main():
    data = build()
    out = os.path.join(HERE, "test_config_data.json")
    with open(out, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    print("Generated {} ({} configs)".format(out, len(data)))


if __name__ == "__main__":
    main()
