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

    Args:
        name: Name of the rule
        **kwargs: Additional arguments passed to cmake rule
    """
    cache_entries = kwargs.pop("cache_entries", {})
    generate_crosstool_file = kwargs.pop("generate_crosstool_file", False)
    data = kwargs.pop("data", [])
    deps = kwargs.pop("deps", [])

    native.filegroup(
        name = "_{}_toolchain_file".format(name),
        srcs = select({
            "@eros_forge//bazel/toolchain:linux_x86_64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64_cross_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64_cross_arm64.cmake"],
            "@eros_forge//bazel/toolchain:auto_x86_64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64.cmake"],
            "@eros_forge//bazel/toolchain:auto_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64.cmake"],
            "//conditions:default": [],
        }),
        visibility = ["//visibility:private"],
    )

    toolchain_file_target = ":_{}_toolchain_file".format(name)

    # Since rules_foreign_cc's cache_entries doesn't support select,
    # we create both debug and release targets, and an alias that selects
    # between them based on the cmake_build_type define.

    # Release target
    cmake(
        name = "_{}_release".format(name),
        cache_entries = {
            "CMAKE_BUILD_TYPE": "Release",
            "CMAKE_TOOLCHAIN_FILE": "$(execpath {})".format(toolchain_file_target),
        } | cache_entries,
        generate_crosstool_file = generate_crosstool_file,
        data = data + [toolchain_file_target],
        deps = deps,
        **kwargs
    )

    # Debug target
    cmake(
        name = "_{}_debug".format(name),
        cache_entries = {
            "CMAKE_BUILD_TYPE": "Debug",
            "CMAKE_TOOLCHAIN_FILE": "$(execpath {})".format(toolchain_file_target),
        } | cache_entries,
        generate_crosstool_file = generate_crosstool_file,
        data = data + [toolchain_file_target],
        deps = deps,
        **kwargs
    )

    # Alias that selects between debug and release based on --define=cmake_build_type
    native.alias(
        name = name,
        actual = select({
            "@eros_forge//bazel/toolchain:cmake_debug": "_{}_debug".format(name),
            "//conditions:default": "_{}_release".format(name),
        }),
        visibility = kwargs.get("visibility", ["//visibility:public"]),
    )
