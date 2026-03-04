load("@rules_cc//cc:cc_toolchain_config_lib.bzl", "feature", "flag_group", "flag_set", "tool_path")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")

ACTION_NAMES = struct(
    c_compile = "c-compile",
    cpp_compile = "c++-compile",
    linkstamp_compilation = "linkstamp-compilation",
    cc_flags_make_variable = "cc-flags-make-variable",
    cpp_module_compile = "c++-module-compile",
    cpp_module_codegen = "c++-module-codegen",
    cpp_header_parsing = "c++-header-parsing",
    cpp_link_executable = "c++-link-executable",
    cpp_link_dynamic_library = "c++-link-dynamic-library",
    cpp_link_nodeps_dynamic_library = "c++-link-nodeps-dynamic-library",
    cpp_link_static_library = "c++-link-static-library",
    assemble = "assemble",
    preprocess_assemble = "preprocess-assemble",
    ldc_compile = "ldc-compile",
    clang_rt_compile = "clang-rt-compile",
    clang_rt_link = "clang-rt-link",
    d_symbundle = "d-symbundle",
)

def _impl(ctx):
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
    ]

    cxx20_feature = feature(
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
                    flag_group(
                        flags = ["-std=c++20"],
                    ),
                ],
            ),
        ],
    )

    supports_pic_feature = feature(
        name = "supports_pic",
        enabled = True,
    )

    supports_dynamic_linker_feature = feature(
        name = "supports_dynamic_linker",
        enabled = True,
    )

    default_link_flags_feature = feature(
        name = "default_link_flags",
        enabled = True,
        flag_sets = [
            flag_set(
                actions = [
                    ACTION_NAMES.cpp_link_executable,
                    ACTION_NAMES.cpp_link_dynamic_library,
                ],
                flag_groups = [
                    flag_group(
                        flags = [
                            "-lstdc++",
                            "-lm",
                            "-lpthread",
                        ],
                    ),
                ],
            ),
        ],
    )

    # Feature for custom GLIBC path - embeds rpath and dynamic-linker into binaries
    # This allows programs to run on systems with older glibc without manual loader invocation
    # Programs will automatically use /opt/eros/lib/ld-linux-aarch64.so.1 as the dynamic linker
    # IMPORTANT: This feature is disabled by default and should only be enabled for cross-compilation
    # via --features=custom_glibc in the build:cross_arm64 configuration
    custom_glibc_feature = feature(
        name = "custom_glibc",
        enabled = False,  # Disabled by default, only enable for cross-compilation
        flag_sets = [
            flag_set(
                actions = [
                    ACTION_NAMES.cpp_link_executable,
                ],
                flag_groups = [
                    flag_group(
                        flags = [
                            "-Wl,--rpath=/opt/eros/lib",
                            "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1",
                        ],
                    ),
                ],
            ),
        ],
    )

    features = [
        cxx20_feature,
        supports_pic_feature,
        supports_dynamic_linker_feature,
        default_link_flags_feature,
        custom_glibc_feature,
    ]

    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        features = features,
        action_configs = [],
        artifact_name_patterns = [],
        cxx_builtin_include_directories = ctx.attr.cxx_builtin_include_directories,
        tool_paths = tool_paths,
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
