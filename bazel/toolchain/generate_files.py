#!/usr/bin/env python3
# Copyright (c) 2024 EROS Project
#
# Single source of truth for the EROS Forge toolchain definitions.
#
# This script generates, from the embedded TOOLCHAINS table below:
#   - toolchain_data.bzl          (Starlark dict consumed by BUILD.bazel macros)
#   - conan/*.profile             (all Conan host/build/sanitizer profiles)
#   - cmake/*.cmake               (all CMake toolchain files)
#
# All compiler paths, GCC version, sysroot, triples and flags are defined ONCE
# here. To change the GCC version, deployment prefix (/opt/eros) or any tool
# path, edit the table below and re-run:
#
#   python3 bazel/toolchain/generate_files.py
#
# Generated files are checked in (so they are available at Bazel load time and
# are content-addressed for remote cache). Do not edit them by hand.

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

GCC_VERSION = "13"
DEFAULT_SYSROOT = "/opt/eros"
CPPSTD = "gnu20"
LIBCXX = "libstdc++11"
TOOL_BIN_DIR = "/usr/bin"
CROSS_PREFIX = "aarch64-linux-gnu-"

# Tool basenames (in Bazel tool_path order). "g++" maps to file label "gxx".
NATIVE_TOOL_BASENAMES = [
    "gcc", "g++", "ld", "ar", "as", "cpp", "gcov", "nm", "objdump", "strip",
    "objcopy",
]

CONFIGS = {
    "linux_x86_64": {
        "cpu": "x86_64",
        "conan_arch": "x86_64",
        "cmake_processor": "x86_64",
        "target_triple": "x86_64-linux-gnu",
        "host_triple": "x86_64-linux-gnu",
        "compiler_prefix": "",
        "libc": "native",
        "target_libc": "glibc_native",
        "abi_version": "x86_64",
        "abi_libc_version": "native",
        "is_cross": False,
        "toolchain_identifier": "x86_64-linux-gnu-native-toolchain",
        "gcc_lib_dir": "/usr/lib/gcc/x86_64-linux-gnu/13",
        "host_tools_set": "native",
        "sysroot": "",
        "dynamic_linker": "",
        "builtin_includes": [
            "/usr/include/c++/13",
            "/usr/include/x86_64-linux-gnu/c++/13",
            "/usr/include/c++/13/backward",
            "/usr/lib/gcc/x86_64-linux-gnu/13/include",
            "/usr/lib/gcc/x86_64-linux-gnu/13/include-fixed",
            "/usr/include/x86_64-linux-gnu",
            "/usr/include",
        ],
    },
    "linux_arm64": {
        "cpu": "aarch64",
        "conan_arch": "armv8",
        "cmake_processor": "aarch64",
        "target_triple": "aarch64-linux-gnu",
        "host_triple": "aarch64-linux-gnu",
        "compiler_prefix": "",
        "libc": "native",
        "target_libc": "glibc_native",
        "abi_version": "aarch64",
        "abi_libc_version": "native",
        "is_cross": False,
        "toolchain_identifier": "aarch64-linux-gnu-native-toolchain",
        "gcc_lib_dir": "/usr/lib/gcc-cross/aarch64-linux-gnu/13",
        "host_tools_set": "native",
        "sysroot": "",
        "dynamic_linker": "",
        "builtin_includes": [
            "/usr/include/c++/13",
            "/usr/include/aarch64-linux-gnu/c++/13",
            "/usr/include/c++/13/backward",
            "/usr/lib/gcc-cross/aarch64-linux-gnu/13/include",
            "/usr/lib/gcc-cross/aarch64-linux-gnu/13/include-fixed",
            "/usr/aarch64-linux-gnu/include",
            "/usr/include/aarch64-linux-gnu",
            "/usr/include",
        ],
    },
    "linux_x86_64_cross_arm64": {
        "cpu": "aarch64",
        "conan_arch": "armv8",
        "cmake_processor": "aarch64",
        "target_triple": "aarch64-linux-gnu",
        "host_triple": "x86_64-linux-gnu",
        "compiler_prefix": CROSS_PREFIX,
        "libc": "cross",
        "target_libc": "glibc_cross",
        "abi_version": "aarch64",
        "abi_libc_version": "cross",
        "is_cross": True,
        "toolchain_identifier": "aarch64-linux-gnu-cross-x86_64-toolchain",
        "gcc_lib_dir": "/usr/lib/gcc-cross/aarch64-linux-gnu/13",
        "host_tools_set": "cross_arm64",
        "sysroot": DEFAULT_SYSROOT,
        "dynamic_linker": "ld-linux-aarch64.so.1",
        "builtin_includes": [
            "/usr/include/c++/13",
            "/usr/include/aarch64-linux-gnu/c++/13",
            "/usr/include/c++/13/backward",
            "/usr/lib/gcc-cross/aarch64-linux-gnu/13/include",
            "/usr/lib/gcc-cross/aarch64-linux-gnu/13/include-fixed",
            "/usr/aarch64-linux-gnu/include",
            "/usr/include/aarch64-linux-gnu",
            "/usr/include",
        ],
    },
    "linux_arm64_cross_arm64": {
        "cpu": "aarch64",
        "conan_arch": "armv8",
        "cmake_processor": "aarch64",
        "target_triple": "aarch64-linux-gnu",
        "host_triple": "aarch64-linux-gnu",
        "compiler_prefix": CROSS_PREFIX,
        "libc": "cross",
        "target_libc": "glibc_cross",
        "abi_version": "aarch64",
        "abi_libc_version": "cross",
        "is_cross": True,
        "toolchain_identifier": "aarch64-linux-gnu-cross-arm64-toolchain",
        "gcc_lib_dir": "/usr/lib/gcc/aarch64-linux-gnu/13",
        "host_tools_set": "cross_arm64",
        "sysroot": DEFAULT_SYSROOT,
        "dynamic_linker": "ld-linux-aarch64.so.1",
        "builtin_includes": [
            "/usr/include/c++/13",
            "/usr/include/aarch64-linux-gnu/c++/13",
            "/usr/include/c++/13/backward",
            "/usr/lib/gcc/aarch64-linux-gnu/13/include",
            "/usr/lib/gcc/aarch64-linux-gnu/13/include-fixed",
            "/usr/aarch64-linux-gnu/include",
            "/usr/include/aarch64-linux-gnu",
            "/usr/include",
        ],
    },
}

# Build-machine descriptor for each cross config (build profile = native build machine).
BUILD_MACHINE = {
    "linux_x86_64_cross_arm64": {
        "conan_arch": "x86_64",
        "cmake_processor": "x86_64",
        "comment": "x86_64 native",
    },
    "linux_arm64_cross_arm64": {
        "conan_arch": "armv8",
        "cmake_processor": "aarch64",
        "comment": "ARM64 native",
    },
}

SANITIZERS = {
    "asan": {"flag": "address", "label": "AddressSanitizer", "desc": "Detects memory errors"},
    "tsan": {"flag": "thread", "label": "ThreadSanitizer", "desc": "Detects data races and deadlocks"},
    "msan": {"flag": "memory", "label": "MemorySanitizer", "desc": "Detects uninitialized memory reads"},
}


def tool_path(cfg, basename):
    prefix = cfg["compiler_prefix"]
    return "{}/{}{}".format(TOOL_BIN_DIR, prefix, basename)


def cross_link_flags(cfg, sanitizer=None):
    """Link flags for cross configs (shared by exelinkflags/sharedlinkflags)."""
    flags = [
        "-B",
        "{}/{}".format(TOOL_BIN_DIR, CROSS_PREFIX),
        "-L{}".format(cfg["gcc_lib_dir"]),
        "-L/usr/aarch64-linux-gnu/lib",
        "-L/usr/lib/aarch64-linux-gnu",
        "-Wl,--rpath={}/lib".format(DEFAULT_SYSROOT),
        "-Wl,--dynamic-linker={}/lib/{}".format(DEFAULT_SYSROOT, cfg["dynamic_linker"]),
    ]
    if sanitizer:
        flags.append("-fsanitize={}".format(SANITIZERS[sanitizer]["flag"]))
    return flags


def cross_compile_flags(sanitizer=None):
    flags = ["-B", "{}/{}".format(TOOL_BIN_DIR, CROSS_PREFIX)]
    if sanitizer:
        flags += ["-O0", "-g", "-fsanitize={}".format(SANITIZERS[sanitizer]["flag"])]
    else:
        flags += ["-O3", "-DNDEBUG"]
    return flags


def native_compile_flags(build_type, sanitizer=None):
    if sanitizer:
        return ["-O0", "-g", "-fsanitize={}".format(SANITIZERS[sanitizer]["flag"])]
    if build_type == "Debug":
        return ["-O0", "-g"]
    return ["-O3", "-DNDEBUG"]


def native_link_flags(sanitizer):
    return ["-fsanitize={}".format(SANITIZERS[sanitizer]["flag"])]


def _json_list(flags):
    return json.dumps(flags)


def _compiler_executables():
    return json.dumps({
        "c": tool_path({"compiler_prefix": CROSS_PREFIX}, "gcc"),
        "cpp": tool_path({"compiler_prefix": CROSS_PREFIX}, "g++"),
        "asm": tool_path({"compiler_prefix": CROSS_PREFIX}, "gcc"),
    })


def _extra_variables():
    tools = {b: tool_path({"compiler_prefix": CROSS_PREFIX}, b) for b in
             ["gcc", "ld", "ar", "objcopy", "objdump", "strip", "nm"]}
    return json.dumps({
        "CMAKE_FIND_ROOT_PATH_MODE_PROGRAM": "NEVER",
        "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY": "ONLY",
        "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE": "ONLY",
        "CMAKE_ASM_COMPILER": tools["gcc"],
        "CMAKE_LINKER": tools["ld"],
        "CMAKE_AR": tools["ar"],
        "CMAKE_OBJCOPY": tools["objcopy"],
        "CMAKE_OBJDUMP": tools["objdump"],
        "CMAKE_STRIP": tools["strip"],
        "CMAKE_NM": tools["nm"],
    })


def _settings_block(conan_arch, build_type):
    lines = [
        "[settings]",
        "arch={}".format(conan_arch),
        "build_type={}".format(build_type),
        "compiler=gcc",
        "compiler.cppstd={}".format(CPPSTD),
        "compiler.version={}".format(GCC_VERSION),
        "compiler.libcxx={}".format(LIBCXX),
        "os=Linux",
    ]
    return lines


def _conf_header(processor):
    return [
        "[conf]",
        "tools.cmake.cmaketoolchain:generator=Unix Makefiles",
        "tools.cmake.cmaketoolchain:system_name=Linux",
        "tools.cmake.cmaketoolchain:system_processor={}".format(processor),
    ]


def gen_native_profile(cfg, name, build_type, sanitizer=None, header_comment=None):
    conan_arch = cfg["conan_arch"]
    processor = cfg["cmake_processor"]
    out = []
    if header_comment:
        out += header_comment + [""]
    out += _settings_block(conan_arch, build_type)
    out += [""]
    out += _conf_header(processor)
    cflags = native_compile_flags(build_type, sanitizer)
    out.append("tools.build:cflags={}".format(_json_list(cflags)))
    out.append("tools.build:cxxflags={}".format(_json_list(cflags)))
    if sanitizer:
        lf = native_link_flags(sanitizer)
        out.append("tools.build:exelinkflags={}".format(_json_list(lf)))
        out.append("tools.build:sharedlinkflags={}".format(_json_list(lf)))
    return "\n".join(out) + "\n"


def gen_cross_host_profile(cfg, name, build_type, sanitizer=None):
    out = [
        "# Host profile for {} cross-compilation".format(_cross_desc(cfg)),
        "# This describes the TARGET machine (ARM64)",
        "",
    ]
    out += _settings_block("armv8", build_type)
    out += [""]
    out += _conf_header("aarch64")
    out.append("tools.build:compiler_executables={}".format(_compiler_executables()))
    out.append("tools.cmake.cmaketoolchain:extra_variables={}".format(_extra_variables()))
    cflags = cross_compile_flags(sanitizer) if build_type == "Release" or sanitizer else \
        ["-B", "{}/{}".format(TOOL_BIN_DIR, CROSS_PREFIX), "-O0", "-g"]
    out.append("tools.build:cflags={}".format(_json_list(cflags)))
    out.append("tools.build:cxxflags={}".format(_json_list(cflags)))
    lf = cross_link_flags(cfg, sanitizer)
    out.append("tools.build:exelinkflags={}".format(_json_list(lf)))
    out.append("tools.build:sharedlinkflags={}".format(_json_list(lf)))
    return "\n".join(out) + "\n"


def gen_cross_build_profile(cfg, name, build_type):
    bm = BUILD_MACHINE[_cross_key(cfg)]
    out = [
        "# Build profile for {} cross-compilation".format(_cross_desc(cfg)),
        "# This describes the BUILD machine ({})".format(bm["comment"]),
        "",
    ]
    out += _settings_block(bm["conan_arch"], build_type)
    out += [""]
    out += _conf_header(bm["cmake_processor"])
    cflags = native_compile_flags(build_type)
    out.append("tools.build:cflags={}".format(_json_list(cflags)))
    out.append("tools.build:cxxflags={}".format(_json_list(cflags)))
    return "\n".join(out) + "\n"


def _cross_key(cfg):
    for k, v in CONFIGS.items():
        if v is cfg:
            return k
    raise RuntimeError("config not found")


def _cross_desc(cfg):
    key = _cross_key(cfg)
    if key == "linux_x86_64_cross_arm64":
        return "x86_64 -> ARM64"
    return "ARM64 -> ARM64 (with custom glibc)"


def generate_conan_profiles():
    profiles = {}
    for key, cfg in CONFIGS.items():
        if not cfg["is_cross"]:
            # native: release, debug, build_release, asan, tsan, msan
            profiles["{}_release".format(key)] = gen_native_profile(cfg, key, "Release")
            profiles["{}_debug".format(key)] = gen_native_profile(cfg, key, "Debug")
            profiles["{}_build_release".format(key)] = gen_native_profile(
                cfg, key, "Release",
                header_comment=["# Build profile for {} native compilation".format(key),
                                "# Same as host profile for native builds"])
            for san in SANITIZERS:
                s = SANITIZERS[san]
                profiles["{}_{}".format(key, san)] = gen_native_profile(
                    cfg, key, "Debug", sanitizer=san,
                    header_comment=["# {} profile for {} native compilation".format(s["label"], key),
                                    "# {}".format(s["desc"])])
        else:
            profiles["{}_host_release".format(key)] = gen_cross_host_profile(cfg, key, "Release")
            profiles["{}_host_debug".format(key)] = gen_cross_host_profile(cfg, key, "Debug")
            profiles["{}_build_release".format(key)] = gen_cross_build_profile(cfg, key, "Release")
            profiles["{}_build_debug".format(key)] = gen_cross_build_profile(cfg, key, "Debug")
            for san in SANITIZERS:
                s = SANITIZERS[san]
                profiles["{}_{}".format(key, san)] = gen_cross_host_profile(
                    cfg, key, "Debug", sanitizer=san)
                # rewrite header for sanitizer profiles
                content = profiles["{}_{}".format(key, san)]
                content = content.replace(
                    "# Host profile for {} cross-compilation".format(_cross_desc(cfg)),
                    "# {} profile for {} cross-compilation".format(s["label"], _cross_desc(cfg)))
                content = content.replace("# This describes the TARGET machine (ARM64)",
                                          "# {}".format(s["desc"]))
                profiles["{}_{}".format(key, san)] = content
    return profiles


def generate_cmake_files():
    files = {}
    for key, cfg in CONFIGS.items():
        files["{}.cmake".format(key)] = gen_cmake_file(cfg, key)
    return files


def gen_cmake_file(cfg, key):
    processor = cfg["cmake_processor"]
    if cfg["is_cross"]:
        exe_lf = " ".join([
            "-L{}".format(cfg["gcc_lib_dir"]),
            "-L/usr/aarch64-linux-gnu/lib",
            "-L/usr/lib/aarch64-linux-gnu",
            "-lstdc++", "-lgcc", "-lm",
            "-Wl,--rpath={}/lib".format(DEFAULT_SYSROOT),
            "-Wl,--dynamic-linker={}/lib/{}".format(DEFAULT_SYSROOT, cfg["dynamic_linker"]),
        ])
        sh_lf = " ".join([
            "-L{}".format(cfg["gcc_lib_dir"]),
            "-L/usr/aarch64-linux-gnu/lib",
            "-L/usr/lib/aarch64-linux-gnu",
            "-lstdc++", "-lgcc", "-lm",
        ])
        out = [
            "# CMake toolchain file for cross-compilation ({})".format(_cross_desc(cfg)),
            "",
            "set(CMAKE_SYSTEM_NAME Linux)",
            "set(CMAKE_SYSTEM_PROCESSOR {})".format(processor),
            "",
            "# Cross-compiler",
            "set(CMAKE_C_COMPILER {})".format(tool_path(cfg, "gcc")),
            "set(CMAKE_CXX_COMPILER {})".format(tool_path(cfg, "g++")),
            "",
            "# Assembler - use gcc as assembler driver with -B flag to find correct tools",
            "set(CMAKE_ASM_COMPILER {})".format(tool_path(cfg, "gcc")),
            "",
            "# Other tools",
            "set(CMAKE_AR {})".format(tool_path(cfg, "ar")),
            "set(CMAKE_LINKER {})".format(tool_path(cfg, "ld")),
            "set(CMAKE_NM {})".format(tool_path(cfg, "nm")),
            "set(CMAKE_OBJCOPY {})".format(tool_path(cfg, "objcopy")),
            "set(CMAKE_OBJDUMP {})".format(tool_path(cfg, "objdump")),
            "set(CMAKE_RANLIB {})".format(tool_path(cfg, "ranlib")),
            "set(CMAKE_STRIP {})".format(tool_path(cfg, "strip")),
            "",
            "# Compiler flags to use correct assembler and tools",
            'set(CMAKE_C_FLAGS "-B{}/{}")'.format(TOOL_BIN_DIR, CROSS_PREFIX),
            'set(CMAKE_CXX_FLAGS "-B{}/{}")'.format(TOOL_BIN_DIR, CROSS_PREFIX),
            'set(CMAKE_ASM_FLAGS "-B{}/{}")'.format(TOOL_BIN_DIR, CROSS_PREFIX),
            "",
            "# Sysroot and library paths",
            "set(CMAKE_FIND_ROOT_PATH /usr/aarch64-linux-gnu)",
            "",
            "# Cross-compilation settings",
            "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)",
            "",
            "# Additional linker flags",
            'set(CMAKE_EXE_LINKER_FLAGS "{}")'.format(exe_lf),
            'set(CMAKE_SHARED_LINKER_FLAGS "{}")'.format(sh_lf),
        ]
    else:
        out = [
            "# CMake toolchain file for native {} compilation".format(processor),
            "# Target: {}".format(cfg["target_triple"]),
            "",
            "set(CMAKE_SYSTEM_NAME Linux)",
            "set(CMAKE_SYSTEM_PROCESSOR {})".format(processor),
            "",
            "# Compilers",
            "set(CMAKE_C_COMPILER {})".format(tool_path(cfg, "gcc")),
            "set(CMAKE_CXX_COMPILER {})".format(tool_path(cfg, "g++")),
            "",
            "# Cross-compilation settings",
            "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)",
            "set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)",
        ]
    return "\n".join(out) + "\n"


def starlark_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def generate_toolchain_data_bzl():
    lines = [
        "# Copyright (c) 2024 EROS Project",
        "# AUTO-GENERATED by generate_files.py. Do not edit by hand.",
        "# Single source of truth: bazel/toolchain/generate_files.py",
        "",
        "GCC_VERSION = {}".format(starlark_string(GCC_VERSION)),
        "DEFAULT_SYSROOT = {}".format(starlark_string(DEFAULT_SYSROOT)),
        "TOOL_BIN_DIR = {}".format(starlark_string(TOOL_BIN_DIR)),
        "CROSS_PREFIX = {}".format(starlark_string(CROSS_PREFIX)),
        "",
        "# Ordered list of native tool basenames (Bazel tool_path order).",
        "NATIVE_TOOL_BASENAMES = [",
    ]
    for b in NATIVE_TOOL_BASENAMES:
        lines.append("    {},".format(starlark_string(b)))
    lines.append("]")
    lines.append("")
    lines.append("EROS_TOOLCHAINS = {")
    for key, cfg in CONFIGS.items():
        lines.append("    {}: {{".format(starlark_string(key)))
        for k in ["cpu", "conan_arch", "cmake_processor", "target_triple", "host_triple",
                  "compiler_prefix", "libc", "target_libc", "abi_version", "abi_libc_version",
                  "toolchain_identifier", "gcc_lib_dir", "host_tools_set", "sysroot",
                  "dynamic_linker"]:
            lines.append("        {}: {},".format(starlark_string(k), starlark_string(cfg[k])))
        lines.append("        \"is_cross\": {},".format("True" if cfg["is_cross"] else "False"))
        lines.append("        \"builtin_includes\": [")
        for inc in cfg["builtin_includes"]:
            lines.append("            {},".format(starlark_string(inc)))
        lines.append("        ],")
        # extra_compile_flags / extra_link_flags (without sysroot rpath/dynamic-linker;
        # those are appended by cc_toolchain_config from the resolved sysroot).
        if cfg["is_cross"]:
            ecf = ["-B{}/{}".format(TOOL_BIN_DIR, CROSS_PREFIX)]
            elf = [
                "-L{}".format(cfg["gcc_lib_dir"]),
                "-L/usr/aarch64-linux-gnu/lib",
                "-L/usr/lib/aarch64-linux-gnu",
                "-lstdc++", "-lgcc", "-lm",
            ]
        else:
            ecf = []
            elf = []
        lines.append("        \"extra_compile_flags\": [")
        for f in ecf:
            lines.append("            {},".format(starlark_string(f)))
        lines.append("        ],")
        lines.append("        \"extra_link_flags\": [")
        for f in elf:
            lines.append("            {},".format(starlark_string(f)))
        lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main():
    # toolchain_data.bzl
    with open(os.path.join(HERE, "toolchain_data.bzl"), "w") as f:
        f.write(generate_toolchain_data_bzl())
    print("Generated toolchain_data.bzl")

    # conan profiles
    conan_dir = os.path.join(HERE, "conan")
    profiles = generate_conan_profiles()
    for name, content in profiles.items():
        with open(os.path.join(conan_dir, name + ".profile"), "w") as f:
            f.write(content)
    print("Generated {} conan profiles".format(len(profiles)))

    # cmake files
    cmake_dir = os.path.join(HERE, "cmake")
    cmake_files = generate_cmake_files()
    for name, content in cmake_files.items():
        with open(os.path.join(cmake_dir, name), "w") as f:
            f.write(content)
    print("Generated {} cmake toolchain files".format(len(cmake_files)))


if __name__ == "__main__":
    main()
