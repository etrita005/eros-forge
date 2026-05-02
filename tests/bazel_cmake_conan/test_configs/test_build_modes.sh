#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

BUILD_MODES=(
    "debug"
    "release"
)

PLATFORM_CONFIG="${1:-linux_x86_64}"

declare -A OPTIMIZATION_MAP=(
    ["debug"]="-O0"
    ["release"]="-O3"
)

declare -A DEFINE_MAP=(
    ["debug"]="DEBUG"
    ["release"]="NDEBUG"
)

declare -A READELF_MAP=(
    ["linux_x86_64"]="readelf"
    ["linux_arm64"]="readelf"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-readelf"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-readelf"
)

READELF_TOOL="${READELF_MAP[$PLATFORM_CONFIG]}"

for mode in "${BUILD_MODES[@]}"; do
    echo "========================================="
    echo "Testing build mode: $mode (platform: $PLATFORM_CONFIG)"
    echo "========================================="
    
    cd "$PROJECT_DIR/src"
    bazel clean
    
    echo ""
    echo "Building with mode: $mode"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=$PLATFORM_CONFIG --config=$mode --subcommands 2>&1 | tee "$BUILD_LOG"
    
    sync
    
    BINARY_PATH=$(find -L bazel-bin -name "hello" -type f -executable ! -path "*_build*" ! -path "*.runfiles*" | head -n1)
    
    if [ -z "$BINARY_PATH" ]; then
        echo "✗ Binary not found"
        exit 1
    fi
    
    echo "Found binary: $BINARY_PATH"
    
    STATIC_LIB_PATH=$(find -L bazel-bin -name "libmylib_static.a" -type f ! -path "*_build*" 2>/dev/null | head -n1)
    SHARED_LIB_PATH=$(find -L bazel-bin -name "libmylib_shared.so" -type f ! -path "*_build*" 2>/dev/null | head -n1)
    
    echo ""
    echo "========================================="
    echo "Build Information from Results"
    echo "========================================="
    
    echo ""
    echo "[Compiler Information]"
    COMPILER_FOUND=$(grep -oE 'Check for working CXX compiler: [^ ]+' "$BUILD_LOG" | head -1 | sed 's/Check for working CXX compiler: //' || echo "")
    if [ -z "$COMPILER_FOUND" ]; then
        COMPILER_FOUND=$(grep -oE '/[a-zA-Z0-9_/.-]+(gcc|g\+\+|clang\+\+|aarch64-linux-gnu-gcc|aarch64-linux-gnu-g\+\+)' "$BUILD_LOG" | head -1 || echo "unknown")
    fi
    echo "  Compiler Path: $COMPILER_FOUND"
    if [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]]; then
        echo "  Compiler Type: Cross-compiler (aarch64)"
    elif [[ $COMPILER_FOUND == *"clang"* ]]; then
        echo "  Compiler Type: Clang"
    else
        echo "  Compiler Type: Native GCC"
    fi
    
    echo ""
    echo "[Compilation Flags]"
    CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$BUILD_LOG" | tail -1 || echo "")
    if [ -z "$CPP_STD" ]; then
        CPP_STD=$(grep -oE 'C\+\+ Standard [0-9]+' "$BUILD_LOG" | head -1 | sed 's/C++ Standard /gnu++/' || echo "unknown")
    fi
    echo "  C++ Standard: $CPP_STD"
    
    OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | head -1 || echo "unknown")
    echo "  Optimization: $OPT_LEVEL"
    
    DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
    echo "  Defines: $DEFINES"
    
    DEBUG_INFO=$(grep -oE '\-g[0-3]?' "$BUILD_LOG" | head -1 || echo "none")
    echo "  Debug Info: $DEBUG_INFO"
    
    echo ""
    echo "[Linker Information]"
    LINKER=$($READELF_TOOL -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    echo ""
    echo "[Symbol Information]"
    SYMBOL_STATUS=$(file "$BINARY_PATH" | grep -oE 'stripped|not stripped' || echo "unknown")
    echo "  Symbol Status: $SYMBOL_STATUS"
    
    echo ""
    echo "========================================="
    echo "Static Library (libmylib_static.a) Verification"
    echo "========================================="
    
    echo ""
    if [ -n "$STATIC_LIB_PATH" ] && [ -f "$STATIC_LIB_PATH" ]; then
        echo "  Path: $STATIC_LIB_PATH"
        STATIC_LIB_SIZE=$(stat -c%s "$STATIC_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $STATIC_LIB_SIZE bytes"
    else
        echo "  Static library not found"
    fi
    
    echo ""
    echo "========================================="
    echo "Shared Library (libmylib_shared.so) Verification"
    echo "========================================="
    
    echo ""
    if [ -n "$SHARED_LIB_PATH" ] && [ -f "$SHARED_LIB_PATH" ]; then
        echo "  Path: $SHARED_LIB_PATH"
        SHARED_LIB_SIZE=$(stat -c%s "$SHARED_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $SHARED_LIB_SIZE bytes"
    else
        echo "  Shared library not found"
    fi
    
    echo ""
    echo "========================================="
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
    echo ""
    if [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]] || [[ $COMPILER_FOUND == *"/bin/c++"* ]] || [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Found: $COMPILER_FOUND"
    else
        echo "✗ Compiler verification FAILED"
        echo "  Found: $COMPILER_FOUND"
        exit 1
    fi
    
    echo ""
    if [[ $CPP_STD == *"c++20"* ]] || [[ $CPP_STD == *"gnu++20"* ]]; then
        echo "✓ C++ standard verification PASSED: $CPP_STD"
    else
        echo "✗ C++ standard verification FAILED"
        echo "  Expected: c++20"
        echo "  Found: $CPP_STD"
        exit 1
    fi
    
    echo ""
    expected_opt="${OPTIMIZATION_MAP[$mode]}"
    if [[ $OPT_LEVEL == *"$expected_opt"* ]] || [[ -z "$OPT_LEVEL" && $mode == "debug" ]]; then
        echo "✓ Optimization level verification PASSED"
        echo "  Expected: $expected_opt"
        echo "  Found: ${OPT_LEVEL:-not specified (default -O0)}"
    else
        echo "⚠ Optimization level verification WARNING"
        echo "  Expected: $expected_opt"
        echo "  Found: $OPT_LEVEL"
    fi
    
    echo ""
    expected_define="${DEFINE_MAP[$mode]}"
    if [ "$mode" == "release" ]; then
        if [[ $DEFINES == *"$expected_define"* ]]; then
            echo "✓ Define verification PASSED"
            echo "  Expected: $expected_define"
            echo "  Found: $DEFINES"
        else
            echo "⚠ Define verification WARNING"
            echo "  Expected: $expected_define"
            echo "  Found: $DEFINES"
        fi
    else
        if [[ $DEFINES != *"NDEBUG"* ]]; then
            echo "✓ Define verification PASSED"
            echo "  Expected: No NDEBUG"
            echo "  Found: $DEFINES"
        else
            echo "⚠ Define verification WARNING"
            echo "  Expected: No NDEBUG"
            echo "  Found: $DEFINES"
        fi
    fi
    
    echo ""
    if [ "$mode" == "release" ]; then
        if [[ $SYMBOL_STATUS == *"stripped"* ]]; then
            echo "✓ Symbol stripping verification PASSED: $SYMBOL_STATUS"
        else
            echo "⚠ Symbol stripping verification WARNING"
            echo "  Expected: stripped"
            echo "  Found: $SYMBOL_STATUS"
        fi
    else
        if [[ $SYMBOL_STATUS == *"not stripped"* ]]; then
            echo "✓ Symbol status verification PASSED: $SYMBOL_STATUS"
        else
            echo "⚠ Symbol status: $SYMBOL_STATUS"
        fi
    fi
    
    if [ -n "$STATIC_LIB_PATH" ] && [ -f "$STATIC_LIB_PATH" ]; then
        echo ""
        echo "✓ Static library verification PASSED"
    fi
    
    if [ -n "$SHARED_LIB_PATH" ] && [ -f "$SHARED_LIB_PATH" ]; then
        echo ""
        echo "✓ Shared library verification PASSED"
    fi
    
    echo ""
    if [[ $PLATFORM_CONFIG != *"cross"* ]]; then
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
    echo "✓ Test PASSED for mode: $mode"
    echo "========================================="
    echo ""
done

echo "========================================="
echo "All build mode tests PASSED!"
echo "========================================="
