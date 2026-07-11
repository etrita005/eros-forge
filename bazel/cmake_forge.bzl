# Copyright (c) 2024 EROS Project
# cmake_forge.bzl - Simplified CMake build rule for EROS
#
# This module provides a simplified cmake rule that uses --config=debug/release
# to control CMAKE_BUILD_TYPE, consistent with Bazel's native workflow.

load("@rules_foreign_cc//foreign_cc:cmake.bzl", "cmake")

def cmake_forge(name, **kwargs):
    """Build a CMake project with toolchain integration.

    This rule automatically selects CMAKE_BUILD_TYPE based on Bazel configuration:
    - --config=debug -> Debug
    - --config=release (or default) -> Release

    A single cmake target is created: CMAKE_BUILD_TYPE is driven by a select()
    on the entire cache_entries dict (each branch is a complete dict with the
    appropriate CMAKE_BUILD_TYPE). This avoids the previous approach of
    instantiating both _{name}_debug and _{name}_release targets, which
    polluted the build graph and was a workaround for the assumption that
    cache_entries could not be configured via select().

    Args:
        name: Name of the rule
        **kwargs: Additional arguments passed to cmake rule
    """
    cache_entries = kwargs.pop("cache_entries", {})
    generate_crosstool_file = kwargs.pop("generate_crosstool_file", False)
    data = kwargs.pop("data", [])
    deps = kwargs.pop("deps", [])
    visibility = kwargs.pop("visibility", ["//visibility:public"])

    native.filegroup(
        name = "_{}_toolchain_file".format(name),
        srcs = select({
            "@eros_forge//bazel/toolchain:linux_x86_64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64_cross_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64_cross_arm64.cmake"],
            "//conditions:default": [],
        }),
        visibility = ["//visibility:private"],
    )

    toolchain_file_target = ":_{}_toolchain_file".format(name)

    # Base cache entries shared by all build modes. User-provided cache_entries
    # are merged here; CMAKE_BUILD_TYPE is intentionally NOT taken from the user
    # — the select() below overrides it so the macro fully controls build mode.
    base_cache_entries = {
        "CMAKE_TOOLCHAIN_FILE": "$(execpath {})".format(toolchain_file_target),
    }
    base_cache_entries.update(cache_entries)

    # Single cmake target: the entire cache_entries dict is a select() so that
    # CMAKE_BUILD_TYPE varies with --config=debug (cmake_build_type=Debug define
    # set by the debug bazelrc config). Each branch is a complete dict; Bazel
    # resolves the select at analysis time and expands $(execpath ...) make
    # variables in the chosen branch's string values.
    cmake(
        name = name,
        cache_entries = select({
            "@eros_forge//bazel/toolchain:cmake_debug": dict(base_cache_entries, CMAKE_BUILD_TYPE = "Debug"),
            "//conditions:default": dict(base_cache_entries, CMAKE_BUILD_TYPE = "Release"),
        }),
        generate_crosstool_file = generate_crosstool_file,
        data = data + [toolchain_file_target],
        deps = deps,
        visibility = visibility,
        **kwargs
    )
