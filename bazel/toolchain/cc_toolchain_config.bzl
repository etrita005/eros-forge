load("@rules_cc//cc:cc_toolchain_config_lib.bzl", "feature", "flag_group", "flag_set", "tool_path")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")

ACTION_NAMES = struct(
    c_compile = "c-compile",
    cpp_compile = "c++-compile",
    cpp_link_executable = "c++-link-executable",
    cpp_link_dynamic_library = "c++-link-dynamic-library",
    cpp_link_nodeps_dynamic_library = "c++-link-nodeps-dynamic-library",
    cpp_module_compile = "c++-module-compile",
    cpp_header_parsing = "c++-header-parsing",
    preprocessing_assemble = "preprocess-assemble",
    assemble = "assemble",
    strip = "strip",
)

def _impl(ctx):
    all_compile_actions = [
        ACTION_NAMES.c_compile,
        ACTION_NAMES.cpp_compile,
        ACTION_NAMES.cpp_module_compile,
        ACTION_NAMES.cpp_header_parsing,
    ]

    # Assembly actions are tracked separately: flags that must reach the
    # assembler driver (e.g. the cross -B prefix that lets aarch64-linux-gnu-gcc
    # find aarch64-linux-gnu-as) need to cover assembly too, whereas
    # C/C++-only flags (sanitizers, dependency_file, opt/dbg) must not.
    all_compile_and_assemble_actions = all_compile_actions + [
        ACTION_NAMES.preprocessing_assemble,
        ACTION_NAMES.assemble,
    ]

    all_link_actions = [
        ACTION_NAMES.cpp_link_executable,
        ACTION_NAMES.cpp_link_dynamic_library,
        ACTION_NAMES.cpp_link_nodeps_dynamic_library,
    ]

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
        # Standard marker features recognised by rules_cc.
        # preprocess-assemble is gcc-driven (.S) and supports -MD -MF, so it is
        # included; plain assemble (as-driven .s) is not (as has no depfile).
        feature(
            name = "dependency_file",
            enabled = True,
            flag_sets = [
                flag_set(
                    actions = all_compile_actions + [
                        ACTION_NAMES.preprocessing_assemble,
                    ],
                    flag_groups = [
                        flag_group(
                            flags = ["-MD", "-MF", "%{dependency_file}"],
                            expand_if_available = "dependency_file",
                        ),
                    ],
                ),
            ],
        ),
        feature(
            name = "static_link_cpp_runtimes",
            enabled = False,
            flag_sets = [
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["-static-libstdc++", "-static-libgcc"]),
                    ],
                ),
            ],
        ),
        # Optimization flags (-O3 -DNDEBUG -g) are driven by bazelrc copts so
        # they apply uniformly to every selected cc toolchain (including the
        # rules_cc auto-detected native toolchain). The opt feature only keeps
        # frame-pointer retention for usable release backtraces.
        feature(
            name = "opt",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = ["-fno-omit-frame-pointer"]),
                    ],
                ),
            ],
        ),
        # Debug flags (-g -O0) are driven by bazelrc copts (see build:debug).
        feature(name = "dbg"),
        feature(
            name = "coverage",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = ["--coverage", "-fprofile-arcs", "-ftest-coverage"]),
                    ],
                ),
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["--coverage"]),
                    ],
                ),
            ],
        ),
        feature(
            name = "asan",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = [
                            "-fsanitize=address",
                            "-fno-omit-frame-pointer",
                            "-fno-optimize-sibling-calls",
                            "-g",
                            "-O1",
                        ]),
                    ],
                ),
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["-fsanitize=address"]),
                    ],
                ),
            ],
        ),
        feature(
            name = "tsan",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = [
                            "-fsanitize=thread",
                            "-fno-omit-frame-pointer",
                            "-fno-optimize-sibling-calls",
                            "-g",
                            "-O1",
                        ]),
                    ],
                ),
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["-fsanitize=thread"]),
                    ],
                ),
            ],
        ),
        feature(
            name = "ubsan",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = [
                            "-fsanitize=undefined",
                            "-fno-omit-frame-pointer",
                            "-g",
                            "-O1",
                        ]),
                    ],
                ),
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["-fsanitize=undefined"]),
                    ],
                ),
            ],
        ),
        feature(
            name = "msan",
            flag_sets = [
                flag_set(
                    actions = all_compile_actions,
                    flag_groups = [
                        flag_group(flags = [
                            "-fsanitize=memory",
                            "-fno-omit-frame-pointer",
                            "-g",
                            "-O1",
                        ]),
                    ],
                ),
                flag_set(
                    actions = all_link_actions,
                    flag_groups = [
                        flag_group(flags = ["-fsanitize=memory"]),
                    ],
                ),
            ],
        ),
    ]

    # Resolve the deployment sysroot. --define=eros_sysroot=... overrides the
    # per-toolchain default (DEFAULT_SYSROOT, typically /opt/eros). The sysroot
    # is used to embed the target dynamic linker and RUNPATH; it is NOT passed
    # as --sysroot (the cross toolchain's default sysroot is kept) so that
    # system headers/libraries are still found via the host cross toolchain.
    sysroot = ctx.var.get("eros_sysroot") or ctx.attr.sysroot_default

    if sysroot:
        features.append(
            feature(
                name = "sysroot",
                enabled = True,
                flag_sets = [
                    flag_set(
                        actions = all_link_actions,
                        flag_groups = [
                            flag_group(flags = [
                                "-Wl,--rpath=" + sysroot + "/lib",
                                "-Wl,--dynamic-linker=" + sysroot + "/lib/" + ctx.attr.dynamic_linker_basename,
                            ]),
                        ],
                    ),
                ],
            )
        )

    if ctx.attr.extra_link_flags:
        features.append(
            feature(
                name = "extra_link_flags",
                enabled = True,
                flag_sets = [
                    flag_set(
                        actions = all_link_actions,
                        flag_groups = [
                            flag_group(flags = ctx.attr.extra_link_flags),
                        ],
                    ),
                ],
            )
        )

    if ctx.attr.extra_compile_flags:
        features.append(
            feature(
                name = "extra_compile_flags",
                enabled = True,
                flag_sets = [
                    flag_set(
                        actions = all_compile_and_assemble_actions,
                        flag_groups = [
                            flag_group(flags = ctx.attr.extra_compile_flags),
                        ],
                    ),
                ],
            )
        )

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
            tool_path(name = "as", path = ctx.attr.as_path),
            tool_path(name = "cpp", path = ctx.attr.cpp_path),
            tool_path(name = "gcov", path = ctx.attr.gcov_path),
            tool_path(name = "nm", path = ctx.attr.nm_path),
            tool_path(name = "objdump", path = ctx.attr.objdump_path),
            tool_path(name = "strip", path = ctx.attr.strip_path),
            tool_path(name = "objcopy", path = ctx.attr.objcopy_path),
            tool_path(name = "dwp", path = ctx.attr.dwp_path),
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
        "as_path": attr.string(mandatory = True),
        "cpp_path": attr.string(mandatory = True),
        "gcov_path": attr.string(mandatory = True),
        "nm_path": attr.string(mandatory = True),
        "objdump_path": attr.string(mandatory = True),
        "strip_path": attr.string(mandatory = True),
        "objcopy_path": attr.string(mandatory = True),
        "dwp_path": attr.string(mandatory = True),
        "cxx_builtin_include_directories": attr.string_list(mandatory = True),
        "sysroot_default": attr.string(default = ""),
        "dynamic_linker_basename": attr.string(default = ""),
        "extra_compile_flags": attr.string_list(default = []),
        "extra_link_flags": attr.string_list(default = []),
    },
    provides = [CcToolchainConfigInfo],
)
