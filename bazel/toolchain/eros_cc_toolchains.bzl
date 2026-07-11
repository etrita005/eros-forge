"""Table-driven instantiation of EROS cc toolchains.

This macro collapses the four hand-written cc_toolchain_config / cc_toolchain /
toolchain blocks (previously duplicated with hardcoded paths) into a single
definition driven by the generated EROS_TOOLCHAINS table in toolchain_data.bzl.

All compiler paths, GCC version, sysroot and triples come from the table (the
single source of truth maintained via generate_files.py). The deployment sysroot
can be overridden at build time with --define=eros_sysroot=... (handled inside
cc_toolchain_config.bzl).
"""

load(":cc_toolchain_config.bzl", "cc_toolchain_config")
load(":toolchain_data.bzl", "EROS_TOOLCHAINS", "TOOL_BIN_DIR")
load("@rules_cc//cc:defs.bzl", "cc_toolchain")

def _tool_path(cfg, basename):
    return "{}/{}{}".format(TOOL_BIN_DIR, cfg["compiler_prefix"], basename)

def eros_cc_toolchain(name, toolchain_name, config_key, exec_compatible_with, target_compatible_with, host_tools):
    """Instantiate a cc_toolchain_config + cc_toolchain + toolchain from the table.

    Args:
        name: name for the cc_toolchain target (and config target prefix).
        toolchain_name: name for the registered toolchain() target.
        config_key: key into EROS_TOOLCHAINS (e.g. "linux_x86_64_cross_arm64").
        exec_compatible_with: constraints for the execution platform.
        target_compatible_with: constraints for the target platform.
        host_tools: label of the host_tools filegroup declaring tool binaries.
    """
    cfg = EROS_TOOLCHAINS[config_key]

    cc_toolchain_config(
        name = name + "_config",
        cpu = cfg["cpu"],
        compiler = "gcc",
        target_system_name = cfg["target_triple"],
        target_libc = cfg["target_libc"],
        abi_version = cfg["abi_version"],
        abi_libc_version = cfg["abi_libc_version"],
        toolchain_identifier = cfg["toolchain_identifier"],
        host_system_name = cfg["host_triple"],
        gcc_path = _tool_path(cfg, "gcc"),
        gxx_path = _tool_path(cfg, "g++"),
        ld_path = _tool_path(cfg, "ld"),
        ar_path = _tool_path(cfg, "ar"),
        as_path = _tool_path(cfg, "as"),
        cpp_path = _tool_path(cfg, "cpp"),
        gcov_path = _tool_path(cfg, "gcov"),
        nm_path = _tool_path(cfg, "nm"),
        objdump_path = _tool_path(cfg, "objdump"),
        strip_path = _tool_path(cfg, "strip"),
        objcopy_path = _tool_path(cfg, "objcopy"),
        dwp_path = _tool_path(cfg, "dwp"),
        cxx_builtin_include_directories = cfg["builtin_includes"],
        sysroot_default = cfg["sysroot"],
        dynamic_linker_basename = cfg["dynamic_linker"],
        extra_compile_flags = cfg["extra_compile_flags"],
        extra_link_flags = cfg["extra_link_flags"],
        visibility = ["//visibility:public"],
    )

    cc_toolchain(
        name = name,
        toolchain_config = ":" + name + "_config",
        all_files = host_tools,
        compiler_files = host_tools,
        dwp_files = host_tools,
        linker_files = host_tools,
        objcopy_files = host_tools,
        strip_files = host_tools,
        supports_param_files = 1,
        visibility = ["//visibility:public"],
    )

    native.toolchain(
        name = toolchain_name,
        exec_compatible_with = exec_compatible_with,
        target_compatible_with = target_compatible_with,
        toolchain = ":" + name,
        toolchain_type = "@rules_cc//cc:toolchain_type",
        visibility = ["//visibility:public"],
    )
