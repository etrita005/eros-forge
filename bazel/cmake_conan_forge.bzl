
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

load("@rules_cc//cc:defs.bzl", "cc_library")

load("@rules_cc//cc:defs.bzl", "CcInfo", "cc_common")

def _conan_install_impl(ctx):
    """Implementation of conan_install rule.

    Runs `conan install` with an isolated CONAN_HOME (so the user's ~/.conan2
    cache is never touched or polluted) and with the conanfile copied into the
    output directory. Copying the conanfile means Conan treats the output dir
    (not the source tree) as the project root, so it never writes
    CMakeUserPresets.json into the source tree. The conan executable is a
    declared action input (copied into @eros_host_tools at fetch time).
    """
    output_dir = ctx.actions.declare_directory("conan_output_{}".format(ctx.attr.name))

    host_profile = ctx.file.host_profile
    build_profile = ctx.file.build_profile
    conan_tool = ctx.executable.conan_tool

    script = ctx.actions.declare_file("conan_install_{}.sh".format(ctx.attr.name))

    script_content = """#!/bin/bash
set -e

CONAN_TOOL="$1"
CONANFILE_SRC="$2"
HOST_PROFILE="$3"
BUILD_PROFILE="$4"
OUTPUT_DIR="$5"

# Resolve all input paths to absolute now (before any cd), since they are
# supplied relative to the action execroot.
CONAN_TOOL="$(realpath "$CONAN_TOOL")"
CONANFILE_SRC="$(realpath "$CONANFILE_SRC")"
HOST_PROFILE="$(realpath "$HOST_PROFILE")"
BUILD_PROFILE="$(realpath "$BUILD_PROFILE")"
OUTPUT_DIR="$(realpath "$OUTPUT_DIR")"

# Ensure HOME is set: the conan entry script imports the conan Python package
# from the user's site-packages, which Python only locates when HOME is set.
if [ -z "$HOME" ]; then
    HOME=$(getent passwd "$(whoami)" 2>/dev/null | cut -d: -f6)
fi
if [ -z "$HOME" ]; then
    HOME="/tmp"
fi
export HOME

# Isolate Conan's cache inside the action workdir so the user's ~/.conan2 is
# never read or written. This makes the action self-contained (no shared,
# mutable host state) which is required for correct remote caching.
export CONAN_HOME="$PWD/_conan_home_{name}"
mkdir -p "$CONAN_HOME"

# Copy the conanfile into the output dir so Conan uses the output dir as the
# project root (no CMakeLists.txt there => no CMakeUserPresets.json written,
# and the source tree is never modified).
CONANFILE_BASENAME="$(basename "$CONANFILE_SRC")"
cp "$CONANFILE_SRC" "$OUTPUT_DIR/$CONANFILE_BASENAME"

cd "$OUTPUT_DIR"
echo "Running: $CONAN_TOOL install ./$CONANFILE_BASENAME --output-folder=$OUTPUT_DIR --build=missing --profile:host=$HOST_PROFILE --profile:build=$BUILD_PROFILE"
"$CONAN_TOOL" install "./$CONANFILE_BASENAME" \
    --output-folder="$OUTPUT_DIR" \
    --build=missing \
    --profile:host="$HOST_PROFILE" \
    --profile:build="$BUILD_PROFILE"
""".format(name = ctx.attr.name)

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    inputs = [ctx.file.conanfile, script, host_profile, build_profile, conan_tool]

    ctx.actions.run_shell(
        outputs = [output_dir],
        inputs = inputs,
        arguments = [
            conan_tool.path,
            ctx.file.conanfile.path,
            host_profile.path,
            build_profile.path,
            output_dir.path,
        ],
        command = "bash {} \"$@\"".format(script.path),
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
        "conan_tool": attr.label(
            default = Label("@eros_host_tools//:conan_tool"),
            allow_single_file = True,
            executable = True,
            cfg = "exec",
            doc = "Conan executable (declared action input, from @eros_host_tools).",
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
    else:
        executable = ctx.actions.declare_file("_{}_dummy".format(ctx.attr.name))
        outputs.append(executable)
    
    for lib in ctx.attr.out_static_libs:
        outputs.append(ctx.actions.declare_file(lib))
    
    for lib in ctx.attr.out_shared_libs:
        outputs.append(ctx.actions.declare_file(lib))
    
    if ctx.attr.out_headers:
        outputs.append(ctx.actions.declare_directory(ctx.attr.out_headers))
    
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

    include_dirs = []
    library_dirs = []
    dep_files = []
    for dep in ctx.attr.deps:
        cc_info = dep[CcInfo]
        compilation_context = cc_info.compilation_context
        for include in compilation_context.includes.to_list():
            include_dirs.append(include)
        linking_context = cc_info.linking_context
        for linker_input in linking_context.linker_inputs.to_list():
            for lib in linker_input.libraries:
                if lib.static_library:
                    library_dirs.append(lib.static_library.dirname)
                    dep_files.append(lib.static_library)
                if lib.dynamic_library:
                    library_dirs.append(lib.dynamic_library.dirname)
                    dep_files.append(lib.dynamic_library)
                if lib.pic_static_library:
                    library_dirs.append(lib.pic_static_library.dirname)
                    dep_files.append(lib.pic_static_library)
    include_path_str = ":".join([str(p) for p in include_dirs])
    library_path_str = ":".join([str(p) for p in library_dirs])
    
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
HEADERS_DIR="${11}"

# Conan output dir is a declared action input; reference it by absolute path.
# The source tree is NEVER written to (no symlinks, no CMakeUserPresets.json).
CONAN_OUTPUT_DIR_ABS="$(pwd)/$CONAN_OUTPUT_DIR"

echo "Source dir: $SOURCE_DIR"
echo "Build dir: $BUILD_DIR"
echo "Conan output dir: $CONAN_OUTPUT_DIR_ABS"
echo "CMake preset: $CMAKE_PRESET"
echo "Headers dir: $HEADERS_DIR"

# Configure using the Conan-generated toolchain directly. find_package() (e.g.
# fmt) resolves via CMAKE_PREFIX_PATH pointing at the Conan output dir, so no
# files need to be copied or symlinked into the source tree.
if [ "$CMAKE_PRESET" = "conan-release" ]; then
    CMAKE_BUILD_TYPE="Release"
else
    CMAKE_BUILD_TYPE="Debug"
fi
cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$CONAN_OUTPUT_DIR_ABS/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" \
    -DCMAKE_POLICY_DEFAULT_CMP0091=NEW \
    -G "Unix Makefiles" \
    -DCMAKE_PREFIX_PATH:PATH="$CONAN_OUTPUT_DIR_ABS" \
    -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR_ABS" \
    ${CMAKE_INCLUDE_PATH:+-DCMAKE_INCLUDE_PATH="$CMAKE_INCLUDE_PATH"} \
    ${CMAKE_LIBRARY_PATH:+-DCMAKE_LIBRARY_PATH="$CMAKE_LIBRARY_PATH"}

# Build all targets
cmake --build "$BUILD_DIR" -j10

# Copy executable
if [ -n "$OUTPUT_EXE" ] && [ "$OUTPUT_EXE" != "" ]; then
    find "$BUILD_DIR" -name "$TARGET_NAME" -type f -executable -exec cp {} "$OUTPUT_EXE" \\;

    # Strip binary in release mode
    if [ "$STRIP_BINARY" = "true" ] && [ -f "$OUTPUT_EXE" ]; then
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
    # First try exact match (may be a symlink)
    exact_match=$(find "$BUILD_DIR" -name "$lib" -print -quit)
    if [ -n "$exact_match" ]; then
        # If it's a symlink, resolve it and copy the real file
        if [ -L "$exact_match" ]; then
            real_file=$(readlink -f "$exact_match")
            cp -f "$real_file" "$(dirname "$BUILD_DIR")/$lib"
        else
            cp -f "$exact_match" "$(dirname "$BUILD_DIR")/$lib"
        fi
    else
        # Try versioned shared library and copy it
        versioned=$(find "$BUILD_DIR" -name "$lib.*" -type f -print -quit)
        if [ -n "$versioned" ]; then
            cp -f "$versioned" "$(dirname "$BUILD_DIR")/$lib"
        fi
    fi
done

# Copy headers
if [ -n "$HEADERS_DIR" ] && [ "$HEADERS_DIR" != "" ]; then
    HEADER_OUTPUT_DIR="$(dirname "$BUILD_DIR")/$HEADERS_DIR"
    mkdir -p "$HEADER_OUTPUT_DIR"
    # Try to find include directories in ExternalProject source dirs
    for src_dir in "$BUILD_DIR"/*-prefix/src/*; do
        if [ -d "$src_dir/include" ]; then
            cp -r "$src_dir/include/"* "$HEADER_OUTPUT_DIR/"
        fi
    done
    # Also check build dir itself
    if [ -d "$BUILD_DIR/include" ]; then
        cp -r "$BUILD_DIR/include/"* "$HEADER_OUTPUT_DIR/"
    fi
fi

# Create dummy executable if no binary was produced
if [ -n "$OUTPUT_EXE" ] && [ ! -f "$OUTPUT_EXE" ]; then
    echo "#!/bin/bash" > "$OUTPUT_EXE"
    chmod +x "$OUTPUT_EXE"
fi
"""

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    ctx.actions.run_shell(
        outputs = [build_dir] + outputs,
        inputs = ctx.attr.conan_deps[DefaultInfo].files.to_list() + srcs + [cmake_lists, script] + dep_files,
        command = 'export CMAKE_INCLUDE_PATH="{}" && export CMAKE_LIBRARY_PATH="{}" && bash {} {} {} {} {} {} "{}" "{}" "{}" "{}" "{}" "{}"'.format(
            include_path_str,
            library_path_str,
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
            ctx.attr.out_headers,
        ),
        mnemonic = "CMakeBuild",
        progress_message = "Building with CMake for {}".format(ctx.attr.name),
        use_default_shell_env = True,
        execution_requirements = {
            "local": "1",
        },
    )

    providers = [DefaultInfo(
        files = depset(outputs),
        executable = executable,
    )]

    # Build CcInfo when libraries are produced
    if ctx.attr.out_static_libs or ctx.attr.out_shared_libs:
        cc_toolchain = ctx.attr._cc_toolchain[cc_common.CcToolchainInfo]
        feature_configuration = cc_common.configure_features(
            ctx = ctx,
            cc_toolchain = cc_toolchain,
        )

        libraries_to_link = []
        for lib in outputs:
            if lib.basename.endswith(".a"):
                libraries_to_link.append(cc_common.create_library_to_link(
                    actions = ctx.actions,
                    cc_toolchain = cc_toolchain,
                    static_library = lib,
                ))
            elif lib.basename.endswith(".so"):
                libraries_to_link.append(cc_common.create_library_to_link(
                    actions = ctx.actions,
                    cc_toolchain = cc_toolchain,
                    feature_configuration = feature_configuration,
                    dynamic_library = lib,
                ))

        linking_context = cc_common.create_linking_context(
            linker_inputs = depset([cc_common.create_linker_input(
                owner = ctx.label,
                libraries = depset(libraries_to_link),
                user_link_flags = depset(ctx.attr.linkopts),
            )]),
        )

        compilation_context = None
        if ctx.attr.out_headers:
            header_output_dir = None
            for f in outputs:
                if f.basename == ctx.attr.out_headers:
                    header_output_dir = f
                    break
            if header_output_dir:
                compilation_context = cc_common.create_compilation_context(
                    includes = depset([header_output_dir.path]),
                    headers = depset([header_output_dir]),
                )

        cc_info = CcInfo(
            compilation_context = compilation_context,
            linking_context = linking_context,
        )

        for dep in ctx.attr.deps:
            cc_info = cc_info.merge(dep[CcInfo])

        providers.append(cc_info)

    return providers

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
        "out_headers": attr.string(default = ""),
        "linkopts": attr.string_list(default = []),
        "strip_binary": attr.bool(default = False),
        "strip_tool": attr.string(default = ""),
        "cmake_preset": attr.string(default = "conan-release"),
        "deps": attr.label_list(providers = [CcInfo]),
        "_cc_toolchain": attr.label(
            default = Label("@rules_cc//cc:current_cc_toolchain"),
        ),
    },
    executable = True,
    fragments = ["cpp"],
    toolchains = ["@rules_cc//cc:toolchain_type"],
)

def cmake_conan_forge(name, conanfile, cmake_lists, srcs, target_name = None,
                      out_binary = None, out_static_libs = None, out_shared_libs = None,
                      hdrs = None, includes = None, deps = None, **kwargs):
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
        hdrs: List of header files for cc_library wrapper (optional)
        includes: List of include paths for cc_library wrapper (optional)
        deps: List of dependencies providing CcInfo (optional)
        **kwargs: Additional arguments
    """
    if target_name == None:
        target_name = name

    if out_binary == None:
        if out_static_libs or out_shared_libs:
            out_binary = ""
        else:
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
        "@eros_forge//bazel/toolchain:auto_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_release",
        "@eros_forge//bazel/toolchain:auto_x86_64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_release",
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
        "@eros_forge//bazel/toolchain:auto_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_build_release",
        "@eros_forge//bazel/toolchain:auto_x86_64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_build_release",
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

    out_headers = kwargs.pop("out_headers", "")
    visibility = kwargs.get("visibility", ["//visibility:public"])

    linkopts = kwargs.pop("linkopts", [])

    if deps == None:
        deps = []

    if hdrs:
        cmake_build_name = "_{}_cmake".format(name)
        cmake_build(
            name = cmake_build_name,
            conan_deps = "_{}_conan".format(name),
            cmake_lists = cmake_lists,
            srcs = srcs,
            target_name = target_name,
            out_binary = out_binary,
            out_static_libs = out_static_libs,
            out_shared_libs = out_shared_libs,
            out_headers = out_headers,
            linkopts = linkopts,
            strip_binary = strip_binary,
            strip_tool = strip_tool,
            cmake_preset = cmake_preset,
            deps = deps,
            visibility = ["//visibility:private"],
        )
        cc_library(
            name = name,
            deps = [":{}".format(cmake_build_name)],
            hdrs = hdrs,
            includes = includes,
            visibility = visibility,
        )
    else:
        cmake_build(
            name = name,
            conan_deps = ":_{}_conan".format(name),
            cmake_lists = cmake_lists,
            srcs = srcs,
            target_name = target_name,
            out_binary = out_binary,
            out_static_libs = out_static_libs,
            out_shared_libs = out_shared_libs,
            out_headers = out_headers,
            linkopts = linkopts,
            strip_binary = strip_binary,
            strip_tool = strip_tool,
            cmake_preset = cmake_preset,
            deps = deps,
            visibility = visibility,
        )
