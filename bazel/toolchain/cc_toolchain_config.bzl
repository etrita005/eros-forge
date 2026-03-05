load("@rules_cc//cc:cc_toolchain_config_lib.bzl", "feature", "flag_group", "flag_set", "tool_path")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")

ACTION_NAMES = struct(
    c_compile = "c-compile",
    cpp_compile = "c++-compile",
    cpp_link_executable = "c++-link-executable",
    cpp_module_compile = "c++-module-compile",
    cpp_header_parsing = "c++-header-parsing",
)

def _impl(ctx):
    features = [
        feature(
            name = "c++20",
            enabled = True,
            flag_sets = [
                flag_set(
                    actions = [
                        ACTION_NAMES.cpp_compile,
                        ACTION_NAMES.cpp_module_compile,
                        ACTION_NAMES.cpp_header_parsing,
                    ],
                    flag_groups = [
                        flag_group(flags = ["-std=c++20"]),
                    ],
                ),
            ],
        ),
        feature(name = "supports_pic", enabled = True),
        feature(name = "supports_dynamic_linker", enabled = True),
    ]

    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        features = features,
        action_configs = [],
        artifact_name_patterns = [],
        cxx_builtin_include_directories = ctx.attr.cxx_builtin_include_directories,
        tool_paths = [
            tool_path(name = "gcc", path = ctx.attr.gcc_path),
            tool_path(name = "g++", path = ctx.attr.gxx_path),
            tool_path(name = "ld", path = ctx.attr.ld_path),
            tool_path(name = "ar", path = ctx.attr.ar_path),
            tool_path(name = "cpp", path = ctx.attr.cpp_path),
            tool_path(name = "gcov", path = ctx.attr.gcov_path),
            tool_path(name = "nm", path = ctx.attr.nm_path),
            tool_path(name = "objdump", path = ctx.attr.objdump_path),
            tool_path(name = "strip", path = ctx.attr.strip_path),
        ],
        target_cpu = ctx.attr.cpu,
        target_system_name = ctx.attr.target_system_name,
        compiler = ctx.attr.compiler,
        abi_version = ctx.attr.abi_version,
        abi_libc_version = ctx.attr.abi_libc_version,
        toolchain_identifier = ctx.attr.toolchain_identifier,
        host_system_name = ctx.attr.host_system_name,
        target_libc = ctx.attr.target_libc,
    )

cc_toolchain_config = rule(
    implementation = _impl,
    attrs = {
        "cpu": attr.string(mandatory = True),
        "compiler": attr.string(mandatory = True),
        "target_system_name": attr.string(mandatory = True),
        "target_libc": attr.string(mandatory = True),
        "abi_version": attr.string(mandatory = True),
        "abi_libc_version": attr.string(mandatory = True),
        "toolchain_identifier": attr.string(mandatory = True),
        "host_system_name": attr.string(mandatory = True),
        "gcc_path": attr.string(mandatory = True),
        "gxx_path": attr.string(mandatory = True),
        "ld_path": attr.string(mandatory = True),
        "ar_path": attr.string(mandatory = True),
        "cpp_path": attr.string(mandatory = True),
        "gcov_path": attr.string(mandatory = True),
        "nm_path": attr.string(mandatory = True),
        "objdump_path": attr.string(mandatory = True),
        "strip_path": attr.string(mandatory = True),
        "cxx_builtin_include_directories": attr.string_list(mandatory = True),
    },
    provides = [CcToolchainConfigInfo],
)
