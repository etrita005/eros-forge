
# Copyright (c) 2024 EROS Project
# cmake_conan_forge.bzl - EROS CMake + Conan integration with Bazel toolchain support
#
# This module provides rules for building CMake projects with Conan dependencies,
# automatically generating toolchain files that match Bazel's configuration.
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
#   )

# Custom CMake build implementation (inspired by demo3) to avoid
# compatibility issues with rules_foreign_cc for cross-compilation

def _conan_install_impl(ctx):
    """Implementation of conan_install rule."""
    output_dir = ctx.actions.declare_directory("conan_output_{}".format(ctx.attr.name))
    conan_profile = ctx.actions.declare_file("conan_profile_{}".format(ctx.attr.name))

    # Detect configuration from Bazel
    is_cross_compile = ctx.attr.is_cross_compile
    is_arm64 = ctx.attr.target_cpu in ["aarch64", "arm64"]
    is_x86_64 = ctx.attr.target_cpu in ["x86_64", "amd64"]

    # Determine Conan settings based on Bazel configuration
    conan_arch = "armv8" if is_arm64 else "x86_64"
    conan_build_type = "Debug" if ctx.attr.is_debug else "Release"
    conan_cppstd = "gnu17"  # Use GNU extensions for better compatibility

    # Create Conan profile
    profile_content = """[settings]
arch={arch}
build_type={build_type}
compiler=gcc
compiler.cppstd={cppstd}
compiler.version=13
compiler.libcxx=libstdc++11
os=Linux

[conf]
tools.cmake.cmaketoolchain:generator=Unix Makefiles
tools.build:cflags=[]
tools.build:cxxflags=[]
tools.build:sharedlinkflags=[]
tools.build:exelinkflags=[]
tools.cmake.cmaketoolchain:system_name=Linux
tools.cmake.cmaketoolchain:system_processor={system_processor}
""".format(
        arch = conan_arch,
        build_type = conan_build_type,
        cppstd = conan_cppstd,
        system_processor = "aarch64" if is_arm64 else "x86_64",
    )

    # Add cross-compilation settings if needed
    if is_cross_compile:
        profile_content += """
tools.build:compiler_executables={{"c": "{c_compiler}", "cpp": "{cxx_compiler}"}}
""".format(
            c_compiler = ctx.attr.c_compiler,
            cxx_compiler = ctx.attr.cxx_compiler,
        )

    ctx.actions.write(
        output = conan_profile,
        content = profile_content,
    )

    # Create install script
    script = ctx.actions.declare_file("conan_install_{}.sh".format(ctx.attr.name))
    script_content = """#!/bin/bash
set -e

# Setup environment
if [ -z "$HOME" ]; then
    HOME=$(getent passwd "$(whoami)" | cut -d: -f6)
fi
if [ -z "$HOME" ]; then
    HOME="/tmp"
fi
export HOME

# Find conan
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

export CONAN_HOME="$HOME/.conan2"

OUTPUT_DIR="$1"
CONANFILE="$2"
PROFILE="$3"
IS_CROSS="$4"

if [ "$IS_CROSS" = "1" ]; then
    # ULTIMATE SOLUTION FOR CONAN BUILD: Only create wrappers when cross-compiling
    WRAPPER_DIR=$(mktemp -d)

    # Create GCC wrapper - also filter -m64!
    cat > "$WRAPPER_DIR/gcc-wrapper" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ] && [ "$arg" != "-m64" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-gcc "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/gcc-wrapper"

    # Create G++ wrapper - also filter -m64!
    cat > "$WRAPPER_DIR/g++-wrapper" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ] && [ "$arg" != "-m64" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-g++ "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/g++-wrapper"

    # Create AS wrapper (CRITICAL!)
    cat > "$WRAPPER_DIR/aarch64-linux-gnu-as" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-as "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/aarch64-linux-gnu-as"

    # Also create a symlink named just 'as'
    ln -s "$WRAPPER_DIR/aarch64-linux-gnu-as" "$WRAPPER_DIR/as"

    # Put wrapper directory at BEGINNING of PATH!
    export PATH="$WRAPPER_DIR:$PATH"

    # Set CC and CXX to our wrappers
    export CC="$WRAPPER_DIR/gcc-wrapper"
    export CXX="$WRAPPER_DIR/g++-wrapper"
fi

# Run conan install with profile
"$CONAN_CMD" install "$CONANFILE" --output-folder="$OUTPUT_DIR" --profile:host="$PROFILE" --build=missing

if [ "$IS_CROSS" = "1" ]; then
    # Cleanup wrapper dir
    rm -rf "$WRAPPER_DIR"
fi
"""

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    # Execute conan install
    ctx.actions.run_shell(
        outputs = [output_dir],
        inputs = [ctx.file.conanfile, conan_profile, script],
        command = "bash {} {} {} {} {}".format(
            script.path,
            output_dir.path,
            ctx.file.conanfile.path,
            conan_profile.path,
            "1" if ctx.attr.is_cross_compile else "0",
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
        "target_cpu": attr.string(default = ""),
        "host_cpu": attr.string(default = ""),
        "c_compiler": attr.string(default = "/usr/bin/gcc"),
        "cxx_compiler": attr.string(default = "/usr/bin/g++"),
        "is_debug": attr.bool(default = False),
        "is_cross_compile": attr.bool(default = False),
    },
)

def _generate_cmake_toolchain_impl(ctx):
    """Generate CMake toolchain file based on Bazel configuration."""
    toolchain_file = ctx.actions.declare_file("{}.cmake".format(ctx.attr.name))

    # Get toolchain info from attributes
    c_compiler = ctx.attr.c_compiler
    cxx_compiler = ctx.attr.cxx_compiler
    target_cpu = ctx.attr.target_cpu
    is_cross_compile = ctx.attr.is_cross_compile

    # Generate toolchain content - simple approach that works
    if is_cross_compile and target_cpu in ["aarch64", "arm64"]:
        # Cross-compilation to ARM64 - completely override all assembler detection
        toolchain_content = """# Generated CMake toolchain file for cross-compilation
# Target: aarch64-linux-gnu

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Skip compiler checks since we know our compilers work
set(CMAKE_C_COMPILER_WORKS 1 CACHE INTERNAL "")
set(CMAKE_CXX_COMPILER_WORKS 1 CACHE INTERNAL "")
set(CMAKE_ASM_COMPILER_WORKS 1 CACHE INTERNAL "")
set(CMAKE_ASM_COMPILER_ID_RUN 1 CACHE INTERNAL "")

# Compilers - set them with FORCE to override anything Conan sets
set(CMAKE_C_COMPILER "/usr/bin/aarch64-linux-gnu-gcc" CACHE FILEPATH "C compiler" FORCE)
set(CMAKE_CXX_COMPILER "/usr/bin/aarch64-linux-gnu-g++" CACHE FILEPATH "C++ compiler" FORCE)

# COMPLETELY DISABLE ASSEMBLY LANGUAGE - we don't need it!
set(CMAKE_ASM_COMPILER "/usr/bin/aarch64-linux-gnu-gcc" CACHE FILEPATH "ASM compiler" FORCE)
set(CMAKE_ASM_COMPILE_OBJECT "<CMAKE_ASM_COMPILER> <DEFINES> <INCLUDES> <FLAGS> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "How to compile an asm file")
set(CMAKE_C_COMPILE_OBJECT "<CMAKE_C_COMPILER> <DEFINES> <INCLUDES> <FLAGS> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "How to compile a C file")
set(CMAKE_CXX_COMPILE_OBJECT "<CMAKE_CXX_COMPILER> <DEFINES> <INCLUDES> <FLAGS> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "How to compile a CXX file")

# Disable any assembler-specific flags
set(CMAKE_ASM_SOURCE_FILE_EXTENSIONS "" CACHE INTERNAL "")
set(CMAKE_DEPFILE_FLAGS_ASM "" CACHE INTERNAL "")

# Other tools
set(CMAKE_AR "/usr/bin/aarch64-linux-gnu-ar" CACHE FILEPATH "Archiver" FORCE)
set(CMAKE_LINKER "/usr/bin/aarch64-linux-gnu-ld" CACHE FILEPATH "Linker" FORCE)
set(CMAKE_NM "/usr/bin/aarch64-linux-gnu-nm" CACHE FILEPATH "NM" FORCE)
set(CMAKE_OBJCOPY "/usr/bin/aarch64-linux-gnu-objcopy" CACHE FILEPATH "Objcopy" FORCE)
set(CMAKE_OBJDUMP "/usr/bin/aarch64-linux-gnu-objdump" CACHE FILEPATH "Objdump" FORCE)
set(CMAKE_RANLIB "/usr/bin/aarch64-linux-gnu-ranlib" CACHE FILEPATH "Ranlib" FORCE)
set(CMAKE_STRIP "/usr/bin/aarch64-linux-gnu-strip" CACHE FILEPATH "Strip" FORCE)

# Clear ALL flags - set empty and force
set(CMAKE_C_FLAGS "" CACHE STRING "C flags" FORCE)
set(CMAKE_CXX_FLAGS "" CACHE STRING "CXX flags" FORCE)
set(CMAKE_ASM_FLAGS "" CACHE STRING "ASM flags" FORCE)
set(CMAKE_C_FLAGS_INIT "" CACHE STRING "C flags init" FORCE)
set(CMAKE_CXX_FLAGS_INIT "" CACHE STRING "CXX flags init" FORCE)
set(CMAKE_ASM_FLAGS_INIT "" CACHE STRING "ASM flags init" FORCE)
set(CMAKE_C_FLAGS_RELEASE "" CACHE STRING "C flags release" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE "" CACHE STRING "CXX flags release" FORCE)
set(CMAKE_ASM_FLAGS_RELEASE "" CACHE STRING "ASM flags release" FORCE)
set(CMAKE_EXE_LINKER_FLAGS "" CACHE STRING "Linker flags" FORCE)
set(CMAKE_SHARED_LINKER_FLAGS "" CACHE STRING "Shared linker flags" FORCE)

# Cross-compilation settings
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# Sysroot
set(CMAKE_FIND_ROOT_PATH "/usr/aarch64-linux-gnu")

# Linker flags for cross-compilation
set(CMAKE_EXE_LINKER_FLAGS "-L/usr/lib/gcc/aarch64-linux-gnu/13 -L/usr/aarch64-linux-gnu/lib -L/usr/lib/aarch64-linux-gnu -lstdc++ -lgcc -lm -Wl,--rpath=/opt/eros/lib -Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1" CACHE STRING "Executable linker flags" FORCE)

# CRITICAL: This function will be called AFTER Conan toolchain is included
# It FORCES all flags and settings to be what we want!
macro(force_toolchain_settings)
    message(STATUS "Forcing EROS toolchain settings...")
    
    # Only set compilers if they aren't already set to wrappers
    if(NOT CMAKE_C_COMPILER MATCHES "wrapper")
        set(CMAKE_C_COMPILER "/usr/bin/aarch64-linux-gnu-gcc" CACHE FILEPATH "C compiler" FORCE)
    endif()
    if(NOT CMAKE_CXX_COMPILER MATCHES "wrapper")
        set(CMAKE_CXX_COMPILER "/usr/bin/aarch64-linux-gnu-g++" CACHE FILEPATH "C++ compiler" FORCE)
    endif()
    set(CMAKE_ASM_COMPILER "/usr/bin/aarch64-linux-gnu-gcc" CACHE FILEPATH "ASM compiler" FORCE)
    
    # Force NO flags!
    set(CMAKE_C_FLAGS "" CACHE STRING "C flags" FORCE)
    set(CMAKE_CXX_FLAGS "" CACHE STRING "CXX flags" FORCE)
    set(CMAKE_ASM_FLAGS "" CACHE STRING "ASM flags" FORCE)
    set(CMAKE_C_FLAGS_RELEASE "" CACHE STRING "C flags release" FORCE)
    set(CMAKE_CXX_FLAGS_RELEASE "" CACHE STRING "CXX flags release" FORCE)
    set(CMAKE_ASM_FLAGS_RELEASE "" CACHE STRING "ASM flags release" FORCE)
    
    # Force compile objects WITHOUT any -EL
    set(CMAKE_C_COMPILE_OBJECT "<CMAKE_C_COMPILER> <DEFINES> <INCLUDES> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "" FORCE)
    set(CMAKE_CXX_COMPILE_OBJECT "<CMAKE_CXX_COMPILER> <DEFINES> <INCLUDES> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "" FORCE)
    set(CMAKE_ASM_COMPILE_OBJECT "<CMAKE_ASM_COMPILER> <DEFINES> <INCLUDES> -o <OBJECT> -c <SOURCE>" CACHE INTERNAL "" FORCE)
endmacro()
"""
    elif target_cpu in ["aarch64", "arm64"]:
        # Native ARM64
        toolchain_content = """# Generated CMake toolchain file for native ARM64
# Target: aarch64-linux-gnu

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Compilers
set(CMAKE_C_COMPILER "/usr/bin/gcc" CACHE FILEPATH "C compiler" FORCE)
set(CMAKE_CXX_COMPILER "/usr/bin/g++" CACHE FILEPATH "C++ compiler" FORCE)

# Clear flags
set(CMAKE_C_FLAGS "" CACHE STRING "C flags" FORCE)
set(CMAKE_CXX_FLAGS "" CACHE STRING "CXX flags" FORCE)
set(CMAKE_ASM_FLAGS "" CACHE STRING "ASM flags" FORCE)

# Cross-compilation settings
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
"""
    else:
        # Native x86_64
        toolchain_content = """# Generated CMake toolchain file for native x86_64
# Target: x86_64-linux-gnu

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

# Compilers
set(CMAKE_C_COMPILER "/usr/bin/gcc" CACHE FILEPATH "C compiler" FORCE)
set(CMAKE_CXX_COMPILER "/usr/bin/g++" CACHE FILEPATH "C++ compiler" FORCE)

# Clear flags
set(CMAKE_C_FLAGS "" CACHE STRING "C flags" FORCE)
set(CMAKE_CXX_FLAGS "" CACHE STRING "CXX flags" FORCE)
set(CMAKE_ASM_FLAGS "" CACHE STRING "ASM flags" FORCE)

# Cross-compilation settings
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
"""

    ctx.actions.write(
        output = toolchain_file,
        content = toolchain_content,
    )

    return [DefaultInfo(files = depset([toolchain_file]))]

generate_cmake_toolchain = rule(
    implementation = _generate_cmake_toolchain_impl,
    attrs = {
        "c_compiler": attr.string(mandatory = True),
        "cxx_compiler": attr.string(mandatory = True),
        "target_cpu": attr.string(mandatory = True),
        "is_cross_compile": attr.bool(default = False),
    },
)

def _cmake_build_impl(ctx):
    """Custom CMake build implementation, inspired by demo3."""
    # Get conan output directory
    conan_output_dir = ctx.attr.conan_deps[DefaultInfo].files.to_list()[0]
    
    # Build directory
    build_dir = ctx.actions.declare_directory("{}_build".format(ctx.attr.name))
    
    # Output executable
    executable = ctx.actions.declare_file(ctx.attr.name)
    
    # Find generated toolchain files
    conan_toolchain_file = "{}/conan_toolchain.cmake".format(conan_output_dir.path)
    eros_toolchain_file = ctx.file.eros_toolchain.path
    
    # Collect all source files as inputs
    srcs = ctx.files.srcs
    
    # Get CMakeLists.txt file
    cmake_lists = ctx.file.cmake_lists
    
    # Source file directory
    source_dir = cmake_lists.dirname
    
    # Get compiler info from attributes
    c_compiler = ctx.attr.c_compiler
    cxx_compiler = ctx.attr.cxx_compiler
    is_cross_compile = ctx.attr.is_cross_compile
    target_cpu = ctx.attr.target_cpu
    
    # Create script file to execute cmake build
    script = ctx.actions.declare_file("cmake_build_{}.sh".format(ctx.attr.name))
    script_content = """#!/bin/bash
set -e

SOURCE_DIR="$1"
BUILD_DIR="$2"
CONAN_TOOLCHAIN="$3"
EROS_TOOLCHAIN="$4"
CONAN_OUTPUT_DIR="$5"
TARGET_NAME="$6"
OUTPUT_EXE="$7"
CC="$8"
CXX="$9"
IS_CROSS="${10}"
TARGET_CPU="${11}"

# Convert to absolute paths
CONAN_TOOLCHAIN_ABS="$(pwd)/$CONAN_TOOLCHAIN"
EROS_TOOLCHAIN_ABS="$(pwd)/$EROS_TOOLCHAIN"
CONAN_OUTPUT_DIR_ABS="$(pwd)/$CONAN_OUTPUT_DIR"

echo "Source dir: $SOURCE_DIR"
echo "Build dir: $BUILD_DIR"
echo "Conan toolchain: $CONAN_TOOLCHAIN_ABS"
echo "EROS toolchain: $EROS_TOOLCHAIN_ABS"
echo "Conan output dir: $CONAN_OUTPUT_DIR_ABS"
echo "C compiler: $CC"
echo "C++ compiler: $CXX"
echo "Is cross: $IS_CROSS"
echo "Target CPU: $TARGET_CPU"

WRAPPER_DIR=""

if [ "$IS_CROSS" = "1" ]; then
    # ULTIMATE SOLUTION: Create a compiler wrapper that filters out -EL and -m64 flags!
    WRAPPER_DIR=$(mktemp -d)

    # Create GCC wrapper - also filter -m64!
    cat > "$WRAPPER_DIR/gcc-wrapper" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ] && [ "$arg" != "-m64" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-gcc "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/gcc-wrapper"

    # Create G++ wrapper - also filter -m64!
    cat > "$WRAPPER_DIR/g++-wrapper" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ] && [ "$arg" != "-m64" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-g++ "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/g++-wrapper"

    # Create AS wrapper (CRITICAL!)
    cat > "$WRAPPER_DIR/aarch64-linux-gnu-as" << 'WRAPPER'
#!/bin/bash
args=()
for arg in "$@"; do
    if [ "$arg" != "-EL" ]; then
        args+=("$arg")
    fi
done
exec /usr/bin/aarch64-linux-gnu-as "${args[@]}"
WRAPPER
    chmod +x "$WRAPPER_DIR/aarch64-linux-gnu-as"

    # Also create a symlink named just 'as'
    ln -s "$WRAPPER_DIR/aarch64-linux-gnu-as" "$WRAPPER_DIR/as"

    # Put wrapper directory at BEGINNING of PATH!
    export PATH="$WRAPPER_DIR:$PATH"

    # Set CC and CXX to our wrappers
    export CC="$WRAPPER_DIR/gcc-wrapper"
    export CXX="$WRAPPER_DIR/g++-wrapper"
fi

# CMake configuration - use EROS toolchain as primary toolchain
# Pass Conan toolchain path as an additional variable
CMAKE_ARGS=()
CMAKE_ARGS+=("-S" "$SOURCE_DIR")
CMAKE_ARGS+=("-B" "$BUILD_DIR")
CMAKE_ARGS+=("-DCMAKE_TOOLCHAIN_FILE=$EROS_TOOLCHAIN_ABS")
CMAKE_ARGS+=("-DCONAN_TOOLCHAIN_FILE=$CONAN_TOOLCHAIN_ABS")
CMAKE_ARGS+=("-DCMAKE_PREFIX_PATH=$CONAN_OUTPUT_DIR_ABS")
CMAKE_ARGS+=("-DCMAKE_BUILD_TYPE=Release")

if [ "$IS_CROSS" = "1" ]; then
    CMAKE_ARGS+=("-DCMAKE_C_COMPILER=$WRAPPER_DIR/gcc-wrapper")
    CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=$WRAPPER_DIR/g++-wrapper")
else
    CMAKE_ARGS+=("-DCMAKE_C_COMPILER=$CC")
    CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=$CXX")
fi

cmake "${CMAKE_ARGS[@]}"

# Now build with cmake --build
cmake --build "$BUILD_DIR" --config Release --target "$TARGET_NAME"

# Copy executable
cp "$BUILD_DIR/$TARGET_NAME" "$OUTPUT_EXE"

if [ "$IS_CROSS" = "1" ]; then
    # Cleanup wrapper dir
    rm -rf "$WRAPPER_DIR"
fi
"""

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    # Execute command - use local strategy to allow access to Conan cache
    ctx.actions.run_shell(
        outputs = [build_dir, executable],
        inputs = ctx.attr.conan_deps[DefaultInfo].files.to_list() + srcs + [cmake_lists, script, ctx.file.eros_toolchain],
        command = "bash {} {} {} {} {} {} {} {} {} {} {} {}".format(
            script.path,
            source_dir,
            build_dir.path,
            conan_toolchain_file,
            eros_toolchain_file,
            conan_output_dir.path,
            ctx.attr.target_name,
            executable.path,
            c_compiler,
            cxx_compiler,
            "1" if is_cross_compile else "0",
            target_cpu,
        ),
        mnemonic = "CMakeBuild",
        progress_message = "Building with CMake for {}".format(ctx.attr.name),
        use_default_shell_env = True,
        # Allow access to Conan home directory
        execution_requirements = {
            "local": "1",
        },
    )
    
    # Return executable
    return [
        DefaultInfo(
            executable = executable,
            files = depset([executable]),
        ),
    ]

cmake_build = rule(
    implementation = _cmake_build_impl,
    attrs = {
        "conan_deps": attr.label(mandatory = True),
        "eros_toolchain": attr.label(
            mandatory = True,
            allow_single_file = [".cmake"],
        ),
        "cmake_lists": attr.label(
            mandatory = True,
            allow_single_file = ["CMakeLists.txt"],
        ),
        "srcs": attr.label_list(
            allow_files = [".cpp", ".h", ".hpp", ".c"],
        ),
        "target_name": attr.string(mandatory = True),
        "c_compiler": attr.string(mandatory = True),
        "cxx_compiler": attr.string(mandatory = True),
        "is_cross_compile": attr.bool(default = False),
        "target_cpu": attr.string(mandatory = True),
    },
    executable = True,
)

def cmake_conan_forge(name, conanfile, cmake_lists, srcs, target_name, **kwargs):
    """Build a CMake project with Conan dependencies using Bazel toolchain.

    This macro creates the necessary rules to:
    1. Run conan install to fetch dependencies
    2. Generate a CMake toolchain file matching Bazel's configuration
    3. Build the CMake project with custom build rule (avoids rules_foreign_cc issues)

    Args:
        name: Name of the rule
        conanfile: Label of the conanfile.txt or conanfile.py
        cmake_lists: Label of the CMakeLists.txt
        srcs: List of source files
        target_name: Name of the CMake target to build
        **kwargs: Additional arguments (not used in custom build)
    """

    # Helper function to create the selects
    def _select_config(x86_64_cross_arm64, arm64_cross_arm64, arm64, default):
        return select({
            "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": x86_64_cross_arm64,
            "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": arm64_cross_arm64,
            "@eros_forge//bazel/toolchain:linux_arm64": arm64,
            "//conditions:default": default,
        })

    # Conan install with platform-specific settings
    conan_install(
        name = "_{}_conan".format(name),
        conanfile = conanfile,
        target_cpu = _select_config("aarch64", "aarch64", "aarch64", "x86_64"),
        host_cpu = "x86_64",
        c_compiler = _select_config("/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/gcc", "/usr/bin/gcc"),
        cxx_compiler = _select_config("/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/g++", "/usr/bin/g++"),
        is_debug = select({
            "@eros_forge//bazel/toolchain:cmake_debug": True,
            "//conditions:default": False,
        }),
        is_cross_compile = _select_config(True, True, False, False),
        visibility = ["//visibility:private"],
    )

    # Generate CMake toolchain file
    generate_cmake_toolchain(
        name = "_{}_toolchain".format(name),
        c_compiler = _select_config("/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/gcc", "/usr/bin/gcc"),
        cxx_compiler = _select_config("/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/g++", "/usr/bin/g++"),
        target_cpu = _select_config("aarch64", "aarch64", "aarch64", "x86_64"),
        is_cross_compile = _select_config(True, True, False, False),
        visibility = ["//visibility:private"],
    )

    # Use custom CMake build rule
    cmake_build(
        name = name,
        conan_deps = ":_{}_conan".format(name),
        eros_toolchain = ":_{}_toolchain".format(name),
        cmake_lists = cmake_lists,
        srcs = srcs,
        target_name = target_name,
        c_compiler = _select_config("/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/aarch64-linux-gnu-gcc", "/usr/bin/gcc", "/usr/bin/gcc"),
        cxx_compiler = _select_config("/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/aarch64-linux-gnu-g++", "/usr/bin/g++", "/usr/bin/g++"),
        is_cross_compile = _select_config(True, True, False, False),
        target_cpu = _select_config("aarch64", "aarch64", "aarch64", "x86_64"),
        visibility = ["//visibility:public"],
    )
