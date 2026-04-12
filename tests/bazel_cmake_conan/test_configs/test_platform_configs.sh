#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

PLATFORM_CONFIGS=(
    "linux_x86_64"
    "linux_arm64"
    "linux_x86_64_cross_arm64"
    "linux_arm64_cross_arm64"
)

declare -A ARCH_MAP=(
    ["linux_x86_64"]="x86_64"
    ["linux_arm64"]="aarch64"
    ["linux_x86_64_cross_arm64"]="aarch64"
    ["linux_arm64_cross_arm64"]="aarch64"
)

declare -A COMPILER_MAP=(
    ["linux_x86_64"]="/usr/bin/g++"
    ["linux_arm64"]="/usr/bin/g++"
    ["linux_x86_64_cross_arm64"]="/usr/bin/aarch64-linux-gnu-g++"
    ["linux_arm64_cross_arm64"]="/usr/bin/aarch64-linux-gnu-g++"
)

declare -A DYNAMIC_LINKER_MAP=(
    ["linux_x86_64"]="/lib/ld-linux-x86-64.so.2"
    ["linux_arm64"]="/lib/ld-linux-aarch64.so.1"
    ["linux_x86_64_cross_arm64"]="/opt/eros/lib/ld-linux-aarch64.so.1"
    ["linux_arm64_cross_arm64"]="/opt/eros/lib/ld-linux-aarch64.so.1"
)

declare -A RPATH_MAP=(
    ["linux_x86_64"]=""
    ["linux_arm64"]=""
    ["linux_x86_64_cross_arm64"]="/opt/eros/lib"
    ["linux_arm64_cross_arm64"]="/opt/eros/lib"
)

# If command line arguments are provided, test only the specified configurations
if [ $# -gt 0 ]; then
    PLATFORM_CONFIGS=("$@")
fi

for config in "${PLATFORM_CONFIGS[@]}"; do
    echo "========================================="
    echo "Testing platform config: $config"
    echo "========================================="
    
    cd "$PROJECT_DIR"
    bazel clean
    
    echo ""
    echo "Building with config: $config"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=$config --subcommands 2>&1 | tee "$BUILD_LOG"
    
    BINARY_PATH=$(find bazel-bin -name "hello" -type f -executable | head -n1)
    
    if [ -z "$BINARY_PATH" ]; then
        echo "✗ Binary not found"
        exit 1
    fi
    
    echo ""
    echo "========================================="
    echo "Build Information from Results"
    echo "========================================="
    
    # Extract and display compiler information from build log
    echo ""
    echo "[Compiler Information]"
    COMPILER_FOUND=$(grep -oE '/[a-zA-Z0-9_/.-]+(gcc|g\+\+|clang\+\+|aarch64-linux-gnu-gcc|aarch64-linux-gnu-g\+\+)' "$BUILD_LOG" | head -1 || echo "unknown")
    echo "  Compiler Path: $COMPILER_FOUND"
    if [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]]; then
        echo "  Compiler Type: Cross-compiler (aarch64)"
    elif [[ $COMPILER_FOUND == *"clang"* ]]; then
        echo "  Compiler Type: Clang"
    else
        echo "  Compiler Type: Native GCC"
    fi
    
    # Extract and display compilation flags from build log
    echo ""
    echo "[Compilation Flags]"
    CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$BUILD_LOG" | tail -1 || echo "unknown")
    echo "  C++ Standard: $CPP_STD"
    
    OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | head -1 || echo "unknown")
    echo "  Optimization: $OPT_LEVEL"
    
    DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
    echo "  Defines: $DEFINES"
    
    # Extract and display linker information from binary
    echo ""
    echo "[Linker Information]"
    LINKER=$(readelf -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    # Check for shared library
    echo ""
    echo "[Shared Library]"
    SHARED_LIB=$(find bazel-bin -name "libmylib.so" | head -n1)
    if [ -n "$SHARED_LIB" ]; then
        echo "  Shared Library: $SHARED_LIB"
        SHARED_LIB_ARCH=$(file "$SHARED_LIB" | grep -oE 'x86-64|ARM aarch64' | head -1)
        echo "  Shared Library Arch: $SHARED_LIB_ARCH"
    else
        echo "  Shared Library: not found"
    fi
    
    echo ""
    echo "========================================="
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
    # Verify compiler
    echo ""
    expected_compiler="${COMPILER_MAP[$config]}"
    if [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]] && [[ $expected_compiler == *"aarch64-linux-gnu"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Expected: $expected_compiler"
        echo "  Found: $COMPILER_FOUND"
    elif [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]] && [[ $expected_compiler == *"/usr/bin/g++"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Expected: $expected_compiler"
        echo "  Found: $COMPILER_FOUND"
    else
        echo "✗ Compiler verification FAILED"
        echo "  Expected: $expected_compiler"
        echo "  Found: $COMPILER_FOUND"
        exit 1
    fi
    
    # Verify compilation flags
    echo ""
    if [[ $CPP_STD == *"c++20"* ]] || [[ $CPP_STD == *"gnu++20"* ]]; then
        echo "✓ C++ standard verification PASSED: $CPP_STD"
    else
        echo "✗ C++ standard verification FAILED"
        echo "  Expected: c++20"
        echo "  Found: $CPP_STD"
        exit 1
    fi
    
    # Verify dynamic linker
    echo ""
    expected_linker="${DYNAMIC_LINKER_MAP[$config]}"
    if [[ $LINKER == *"$expected_linker"* ]]; then
        echo "✓ Dynamic linker verification PASSED"
        echo "  Expected: $expected_linker"
        echo "  Found: $LINKER"
    else
        echo "✗ Dynamic linker verification FAILED"
        echo "  Expected: $expected_linker"
        echo "  Found: $LINKER"
        exit 1
    fi
    
    # Verify RPATH (for cross-compilation)
    echo ""
    expected_rpath="${RPATH_MAP[$config]}"
    if [[ -n "$expected_rpath" ]]; then
        if [[ $RPATH == *"$expected_rpath"* ]]; then
            echo "✓ RPATH verification PASSED"
            echo "  Expected: $expected_rpath"
            echo "  Found: $RPATH"
        else
            echo "✗ RPATH verification FAILED"
            echo "  Expected: $expected_rpath"
            echo "  Found: $RPATH"
            exit 1
        fi
    else
        echo "  RPATH verification SKIPPED (not required for this config)"
    fi
    
    # Verify binary architecture
    echo ""
    expected_arch="${ARCH_MAP[$config]}"
    BINARY_ARCH=$(file "$BINARY_PATH" | grep -oE 'x86-64|ARM aarch64' | head -1)
    if [[ $BINARY_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Architecture verification PASSED: x86_64"
    elif [[ $BINARY_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Architecture verification PASSED: aarch64"
    else
        echo "✗ Architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $BINARY_ARCH"
        exit 1
    fi
    
    # Verify shared library
    echo ""
    if [ -n "$SHARED_LIB" ]; then
        echo "✓ Shared library verification PASSED"
    else
        echo "✗ Shared library verification FAILED"
        exit 1
    fi
    
    # Run binary (for native compilation)
    echo ""
    if [[ $config != *"cross"* ]]; then
        if "$BINARY_PATH" >/dev/null 2>&1; then
            echo "✓ Binary execution PASSED"
        else
            echo "✗ Binary execution FAILED"
            exit 1
        fi
    else
        echo "  Binary execution SKIPPED (cross-compiled binary)"
    fi
    
    rm -f "$BUILD_LOG"
    
    echo ""
    echo "========================================="
    echo "✓ Test PASSED for config: $config"
    echo "========================================="
    echo ""
done

echo "========================================="
echo "All platform config tests PASSED!"
echo "========================================="
