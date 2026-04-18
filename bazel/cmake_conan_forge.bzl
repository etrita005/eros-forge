
# Copyright (c) 2024 EROS Project
# cmake_conan_forge.bzl - EROS CMake + Conan integration with Bazel toolchain support
#
# This module provides rules for building CMake projects with Conan dependencies,
# using Conan-generated presets for configuration.
#
# Usage:
#   load("@eros_forge//bazel:cmake_conan_forge.bzl", "cmake_conan_forge")
#
#   cmake_conan_forge(
#       name = "my_cmake_project",
#       conanfile = "conanfile.txt",
#       cmake_lists = "CMakeLists.txt",
#       srcs = glob(["src/**/*.cpp", "src/**/*.h"]),
#       target_name = "my_target",
#       out_static_libs = ["libmylib.a"],
#       out_shared_libs = ["libmylib.so"],
#   )

def _conan_install_impl(ctx):
    """Implementation of conan_install rule.
    
    Uses predefined Conan profiles from eros_forge//bazel/toolchain/conan.
    For cross-compilation, uses separate build and host profiles.
    For native compilation, build and host profiles are the same.
    """
    output_dir = ctx.actions.declare_directory("conan_output_{}".format(ctx.attr.name))
    
    host_profile = ctx.file.host_profile
    build_profile = ctx.file.build_profile
    
    script = ctx.actions.declare_file("conan_install_{}.sh".format(ctx.attr.name))
    
    conan_profile_args = "--profile:host={} --profile:build={}".format(
        host_profile.path,
        build_profile.path,
    )
    
    script_content = """#!/bin/bash
set -e

if [ -z "$HOME" ]; then
    HOME=$(getent passwd "$(whoami)" | cut -d: -f6)
fi
if [ -z "$HOME" ]; then
    HOME="/tmp"
fi
export HOME

CONAN_CMD=""
for path in "$HOME/.local/bin/conan" "/usr/local/bin/conan" "/usr/bin/conan" "conan"; do
    if [ -x "$path" ]; then
        CONAN_CMD="$path"
        break
    fi
done

if [ -z "$CONAN_CMD" ]; then
    echo "Error: conan command not found"
    exit 1
fi

OUTPUT_DIR="$1"
CONANFILE="$2"
PROFILE_ARGS="$3"

echo "Running: $CONAN_CMD install $CONANFILE --output-folder=$OUTPUT_DIR $PROFILE_ARGS --build=missing"
"$CONAN_CMD" install "$CONANFILE" --output-folder="$OUTPUT_DIR" $PROFILE_ARGS --build=missing
"""

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    inputs = [ctx.file.conanfile, script, host_profile, build_profile]
    
    ctx.actions.run_shell(
        outputs = [output_dir],
        inputs = inputs,
        command = "bash {} {} {} '{}'".format(
            script.path,
            output_dir.path,
            ctx.file.conanfile.path,
            conan_profile_args,
        ),
        mnemonic = "ConanInstall",
        progress_message = "Running conan install for {}".format(ctx.attr.name),
        use_default_shell_env = True,
        execution_requirements = {
            "local": "1",
        },
    )

    return [DefaultInfo(files = depset([output_dir]))]

conan_install = rule(
    implementation = _conan_install_impl,
    attrs = {
        "conanfile": attr.label(
            mandatory = True,
            allow_single_file = ["conanfile.txt", "conanfile.py"],
        ),
        "host_profile": attr.label(
            mandatory = True,
            allow_single_file = [".profile"],
        ),
        "build_profile": attr.label(
            mandatory = True,
            allow_single_file = [".profile"],
        ),
    },
)

def _cmake_build_impl(ctx):
    """Custom CMake build implementation using Conan-generated presets."""
    conan_output_dir = ctx.attr.conan_deps[DefaultInfo].files.to_list()[0]
    
    build_dir = ctx.actions.declare_directory("{}_build".format(ctx.attr.name))
    
    outputs = []
    executable = None
    
    if ctx.attr.out_binary:
        executable = ctx.actions.declare_file(ctx.attr.out_binary)
        outputs.append(executable)
    
    for lib in ctx.attr.out_static_libs:
        outputs.append(ctx.actions.declare_file(lib))
    
    for lib in ctx.attr.out_shared_libs:
        outputs.append(ctx.actions.declare_file(lib))
    
    srcs = ctx.files.srcs
    cmake_lists = ctx.file.cmake_lists
    source_dir = cmake_lists.dirname
    
    script = ctx.actions.declare_file("cmake_build_{}.sh".format(ctx.attr.name))
    
    static_libs_args = " ".join(['"{}"'.format(lib) for lib in ctx.attr.out_static_libs])
    shared_libs_args = " ".join(['"{}"'.format(lib) for lib in ctx.attr.out_shared_libs])
    
    strip_binary = ctx.attr.strip_binary
    
    strip_tool = ""
    if ctx.attr.strip_tool:
        strip_tool = ctx.attr.strip_tool
    
    cmake_preset = ctx.attr.cmake_preset
    
    script_content = """#!/bin/bash
set -e

SOURCE_DIR="$1"
BUILD_DIR="$2"
CONAN_OUTPUT_DIR="$3"
TARGET_NAME="$4"
OUTPUT_EXE="$5"
STATIC_LIBS="$6"
SHARED_LIBS="$7"
STRIP_BINARY="$8"
STRIP_TOOL="$9"
CMAKE_PRESET="${10}"

CONAN_OUTPUT_DIR_ABS="$(pwd)/$CONAN_OUTPUT_DIR"

echo "Source dir: $SOURCE_DIR"
echo "Build dir: $BUILD_DIR"
echo "Conan output dir: $CONAN_OUTPUT_DIR_ABS"
echo "CMake preset: $CMAKE_PRESET"

# Create symlinks to ALL Conan-generated files in source directory
# This is needed because CMake preset uses relative paths
for f in "$CONAN_OUTPUT_DIR_ABS"/*; do
    fname=$(basename "$f")
    ln -sf "$f" "$SOURCE_DIR/$fname"
done

# Configure using Conan preset with custom build directory
# Append Conan output dir to CMAKE_FIND_ROOT_PATH for cross-compilation
cmake --preset "$CMAKE_PRESET" -B "$BUILD_DIR" -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR_ABS"

# Build all targets
cmake --build "$BUILD_DIR" -j10

# Copy executable
if [ -n "$OUTPUT_EXE" ] && [ "$OUTPUT_EXE" != "" ]; then
    find "$BUILD_DIR" -name "$TARGET_NAME" -type f -executable -exec cp {} "$OUTPUT_EXE" \\;
    
    # Strip binary in release mode
    if [ "$STRIP_BINARY" = "true" ]; then
        if [ -n "$STRIP_TOOL" ] && [ "$STRIP_TOOL" != "" ]; then
            echo "Stripping binary with $STRIP_TOOL..."
            "$STRIP_TOOL" "$OUTPUT_EXE"
        else
            echo "Stripping binary..."
            strip "$OUTPUT_EXE"
        fi
    fi
fi

# Copy static libraries
for lib in $STATIC_LIBS; do
    find "$BUILD_DIR" -name "$lib" -type f -exec cp {} "$(dirname "$BUILD_DIR")/$lib" \\;
done

# Copy shared libraries
for lib in $SHARED_LIBS; do
    find "$BUILD_DIR" -name "$lib" -type f -exec cp {} "$(dirname "$BUILD_DIR")/$lib" \\;
done

# Cleanup
for f in "$CONAN_OUTPUT_DIR_ABS"/*; do
    fname=$(basename "$f")
    rm -f "$SOURCE_DIR/$fname"
done
"""

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    ctx.actions.run_shell(
        outputs = [build_dir] + outputs,
        inputs = ctx.attr.conan_deps[DefaultInfo].files.to_list() + srcs + [cmake_lists, script],
        command = 'bash {} {} {} {} {} {} "{}" "{}" "{}" "{}" "{}"'.format(
            script.path,
            source_dir,
            build_dir.path,
            conan_output_dir.path,
            ctx.attr.target_name,
            executable.path if executable else "",
            static_libs_args,
            shared_libs_args,
            "true" if strip_binary else "false",
            strip_tool,
            cmake_preset,
        ),
        mnemonic = "CMakeBuild",
        progress_message = "Building with CMake for {}".format(ctx.attr.name),
        use_default_shell_env = True,
        execution_requirements = {
            "local": "1",
        },
    )

    return [DefaultInfo(
        files = depset(outputs),
        executable = executable,
    )]

cmake_build = rule(
    implementation = _cmake_build_impl,
    attrs = {
        "conan_deps": attr.label(mandatory = True),
        "cmake_lists": attr.label(
            mandatory = True,
            allow_single_file = ["CMakeLists.txt"],
        ),
        "srcs": attr.label_list(
            allow_files = [".cpp", ".h", ".hpp", ".c"],
        ),
        "target_name": attr.string(mandatory = True),
        "out_binary": attr.string(default = ""),
        "out_static_libs": attr.string_list(default = []),
        "out_shared_libs": attr.string_list(default = []),
        "strip_binary": attr.bool(default = False),
        "strip_tool": attr.string(default = ""),
        "cmake_preset": attr.string(default = "conan-release"),
    },
    executable = True,
)

def cmake_conan_forge(name, conanfile, cmake_lists, srcs, target_name = None, 
                      out_binary = None, out_static_libs = None, out_shared_libs = None, **kwargs):
    """Build a CMake project with Conan dependencies using Bazel toolchain.

    This macro creates the necessary rules to:
    1. Run conan install with predefined profiles matching Bazel configuration
    2. Build the CMake project using Conan-generated presets

    Args:
        name: Name of the rule (also used as CMake target name by default)
        conanfile: Label of the conanfile.txt or conanfile.py
        cmake_lists: Label of the CMakeLists.txt
        srcs: List of source files
        target_name: Name of the CMake target to build (defaults to name)
        out_binary: Name of the output binary (defaults to target_name)
        out_static_libs: List of static library outputs (e.g., ["libmylib.a"])
        out_shared_libs: List of shared library outputs (e.g., ["libmylib.so"])
        **kwargs: Additional arguments
    """
    if target_name == None:
        target_name = name
    
    if out_binary == None:
        out_binary = target_name
    
    if out_static_libs == None:
        out_static_libs = []
    
    if out_shared_libs == None:
        out_shared_libs = []

    host_profile = select({
        "@eros_forge//bazel/toolchain:linux_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
        "@eros_forge//bazel/toolchain:linux_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
        "@eros_forge//bazel/toolchain:linux_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_tsan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_msan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
        "@eros_forge//bazel/toolchain:linux_x86_64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
        "@eros_forge//bazel/toolchain:linux_x86_64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_tsan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_msan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_host_debug",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_host_release",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_host_debug",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_host_release",
        "@eros_forge//bazel/toolchain:linux_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_debug",
        "@eros_forge//bazel/toolchain:linux_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_release",
        "@eros_forge//bazel/toolchain:linux_x86_64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_debug",
        "//conditions:default": "@eros_forge//bazel/toolchain/conan:linux_x86_64_release",
    })
    
    build_profile = select({
        "@eros_forge//bazel/toolchain:linux_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
        "@eros_forge//bazel/toolchain:linux_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
        "@eros_forge//bazel/toolchain:linux_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
        "@eros_forge//bazel/toolchain:linux_x86_64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
        "@eros_forge//bazel/toolchain:linux_x86_64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_build_debug",
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_build_release",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_build_debug",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_build_release",
        "@eros_forge//bazel/toolchain:linux_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_debug",
        "@eros_forge//bazel/toolchain:linux_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_build_release",
        "@eros_forge//bazel/toolchain:linux_x86_64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_debug",
        "//conditions:default": "@eros_forge//bazel/toolchain/conan:linux_x86_64_build_release",
    })

    strip_tool = select({
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "aarch64-linux-gnu-strip",
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "aarch64-linux-gnu-strip",
        "//conditions:default": "strip",
    })

    strip_binary = select({
        "@eros_forge//bazel/toolchain:tsan": False,
        "@eros_forge//bazel/toolchain:msan": False,
        "@eros_forge//bazel/toolchain:asan": False,
        "@eros_forge//bazel/toolchain:cmake_debug": False,
        "//conditions:default": True,
    })

    cmake_preset = select({
        "@eros_forge//bazel/toolchain:tsan": "conan-debug",
        "@eros_forge//bazel/toolchain:msan": "conan-debug",
        "@eros_forge//bazel/toolchain:asan": "conan-debug",
        "@eros_forge//bazel/toolchain:cmake_debug": "conan-debug",
        "//conditions:default": "conan-release",
    })

    conan_install(
        name = "_{}_conan".format(name),
        conanfile = conanfile,
        host_profile = host_profile,
        build_profile = build_profile,
        visibility = ["//visibility:private"],
    )

    cmake_build(
        name = name,
        conan_deps = ":_{}_conan".format(name),
        cmake_lists = cmake_lists,
        srcs = srcs,
        target_name = target_name,
        out_binary = out_binary,
        out_static_libs = out_static_libs,
        out_shared_libs = out_shared_libs,
        strip_binary = strip_binary,
        strip_tool = strip_tool,
        cmake_preset = cmake_preset,
        visibility = ["//visibility:public"],
    )
