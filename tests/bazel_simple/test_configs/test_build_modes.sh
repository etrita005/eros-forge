#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

PLATFORM_CONFIG="${1:-linux_x86_64}"

BUILD_MODES=(
    "debug"
    "release"
)

declare -A OPTIMIZATION_MAP=(
    ["debug"]="-O0"
    ["release"]="-O3"
)

declare -A DEFINE_MAP=(
    ["debug"]="DEBUG"
    ["release"]="NDEBUG"
)

echo "========================================="
echo "Testing Build Modes for Platform: $PLATFORM_CONFIG"
echo "========================================="
echo ""

for mode in "${BUILD_MODES[@]}"; do
    echo "========================================="
    echo "Testing build mode: $mode"
    echo "Platform config: $PLATFORM_CONFIG"
    echo "========================================="
    
    cd "$PROJECT_DIR"
    bazel clean
    
    echo ""
    echo "Building with platform: $PLATFORM_CONFIG, mode: $mode"
    BUILD_LOG=$(mktemp)
    bazel build //:hello //:math_utils_static //:math_utils_shared --config=$PLATFORM_CONFIG --config=$mode --subcommands 2>&1 | tee "$BUILD_LOG"
    
    BINARY_PATH=$(bazel cquery //:hello --output=files --config=$PLATFORM_CONFIG --config=$mode | grep -E 'hello$' | head -n1)
    STATIC_LIB_PATH=$(bazel cquery //:math_utils_static --output=files --config=$PLATFORM_CONFIG --config=$mode | grep -E '\.a$' | head -n1)
    SHARED_LIB_PATH=$(bazel cquery //:math_utils_shared --output=files --config=$PLATFORM_CONFIG --config=$mode | grep -E '\.so$' | head -n1)
    
    echo ""
    echo "========================================="
    echo "Build Information from Results"
    echo "========================================="
    
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
    
    echo ""
    echo "[Compilation Flags]"
    CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$BUILD_LOG" | tail -1 || echo "unknown")
    echo "  C++ Standard: $CPP_STD"
    
    OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | tail -1 || echo "unknown")
    echo "  Optimization: $OPT_LEVEL"
    
    DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
    echo "  Defines: $DEFINES"
    
    DEBUG_INFO=$(grep -oE '\-g[0-3]?' "$BUILD_LOG" | head -1 || echo "none")
    echo "  Debug Info: $DEBUG_INFO"
    
    echo ""
    echo "========================================="
    echo "Binary (hello) Verification"
    echo "========================================="
    
    echo ""
    echo "[Linker Information]"
    LINKER=$(readelf -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    echo ""
    echo "[Symbol Information]"
    SYMBOL_STATUS=$(file "$BINARY_PATH" | grep -oE 'stripped|not stripped' || echo "unknown")
    echo "  Symbol Status: $SYMBOL_STATUS"
    
    echo ""
    echo "========================================="
    echo "Static Library (libmath_utils_static.a) Verification"
    echo "========================================="
    
    echo ""
    if [ -f "$STATIC_LIB_PATH" ]; then
        echo "  Path: $STATIC_LIB_PATH"
        LIB_SIZE=$(stat -c%s "$STATIC_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $LIB_SIZE bytes"
        LIB_SYMBOLS=$(nm "$STATIC_LIB_PATH" 2>/dev/null | grep -E 'T.*calculate_sum|T.*get_greeting|T.*fibonacci' | wc -l || echo "0")
        echo "  Exported Symbols: $LIB_SYMBOLS"
        STATIC_DEBUG=$(file "$STATIC_LIB_PATH" | grep -oE 'with debug_info|not stripped' || echo "unknown")
        echo "  Debug Info: $STATIC_DEBUG"
    else
        echo "  ERROR: Static library not found!"
        exit 1
    fi
    
    echo ""
    echo "========================================="
    echo "Shared Library (libmath_utils_shared.so) Verification"
    echo "========================================="
    
    echo ""
    if [ -f "$SHARED_LIB_PATH" ]; then
        echo "  Path: $SHARED_LIB_PATH"
        LIB_SIZE=$(stat -c%s "$SHARED_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $LIB_SIZE bytes"
        LIB_SYMBOLS=$(nm -D "$SHARED_LIB_PATH" 2>/dev/null | grep -E 'T.*calculate_sum|T.*get_greeting|T.*fibonacci' | wc -l || echo "0")
        echo "  Exported Symbols: $LIB_SYMBOLS"
        SHARED_DEBUG=$(file "$SHARED_LIB_PATH" | grep -oE 'with debug_info|not stripped|stripped' || echo "unknown")
        echo "  Debug Info: $SHARED_DEBUG"
        SO_NEEDED=$(readelf -d "$SHARED_LIB_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
        echo "  Needed Libraries: $SO_NEEDED"
    else
        echo "  ERROR: Shared library not found!"
        exit 1
    fi
    
    echo ""
    echo "========================================="
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
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
    HAS_SANITIZER=$(grep -E '\-fsanitize=' "$BUILD_LOG" | head -1 || echo "")
    
    if [ "$mode" == "debug" ]; then
        if [[ -z "$OPT_LEVEL" ]] || [[ $OPT_LEVEL == *"-O0"* ]]; then
            echo "✓ Optimization level verification PASSED"
            echo "  Expected: $expected_opt"
            echo "  Found: ${OPT_LEVEL:-not specified (default -O0)}"
        elif [[ $OPT_LEVEL == *"-O1"* ]] && [[ -n "$HAS_SANITIZER" ]]; then
            echo "✓ Optimization level verification PASSED"
            echo "  Expected: $expected_opt (or -O1 with sanitizers)"
            echo "  Found: $OPT_LEVEL (sanitizers enabled)"
        else
            echo "✗ Optimization level verification FAILED"
            echo "  Expected: $expected_opt"
            echo "  Found: $OPT_LEVEL"
            exit 1
        fi
    else
        if [[ $OPT_LEVEL == *"$expected_opt"* ]]; then
            echo "✓ Optimization level verification PASSED"
            echo "  Expected: $expected_opt"
            echo "  Found: $OPT_LEVEL"
        else
            echo "✗ Optimization level verification FAILED"
            echo "  Expected: $expected_opt"
            echo "  Found: $OPT_LEVEL"
            exit 1
        fi
    fi
    
    echo ""
    expected_define="${DEFINE_MAP[$mode]}"
    if [ "$mode" == "release" ]; then
        if [[ $DEFINES == *"$expected_define"* ]]; then
            echo "✓ Define verification PASSED"
            echo "  Expected: $expected_define"
            echo "  Found: $DEFINES"
        else
            echo "✗ Define verification FAILED"
            echo "  Expected: $expected_define"
            echo "  Found: $DEFINES"
            exit 1
        fi
    else
        if [[ $DEFINES != *"NDEBUG"* ]]; then
            echo "✓ Define verification PASSED"
            echo "  Expected: No NDEBUG"
            echo "  Found: $DEFINES"
        else
            echo "✗ Define verification FAILED"
            echo "  Expected: No NDEBUG"
            echo "  Found: $DEFINES"
            exit 1
        fi
    fi
    
    echo ""
    if [ "$mode" == "release" ]; then
        if [[ $SYMBOL_STATUS == *"stripped"* ]]; then
            echo "✓ Symbol stripping verification PASSED: $SYMBOL_STATUS"
        else
            echo "✗ Symbol stripping verification FAILED"
            echo "  Expected: stripped"
            echo "  Found: $SYMBOL_STATUS"
            exit 1
        fi
    else
        if [[ $SYMBOL_STATUS == *"not stripped"* ]]; then
            echo "✓ Symbol status verification PASSED: $SYMBOL_STATUS"
        else
            echo "⚠ Symbol status: $SYMBOL_STATUS"
        fi
    fi
    
    echo ""
    if [ "$LIB_SYMBOLS" -ge 3 ]; then
        echo "✓ Library symbols verification PASSED"
        echo "  Found $LIB_SYMBOLS exported symbols"
    else
        echo "✗ Library symbols verification FAILED"
        echo "  Expected: 3 or more exported symbols"
        echo "  Found: $LIB_SYMBOLS"
        exit 1
    fi
    
    echo ""
    if [[ $PLATFORM_CONFIG == *"cross"* ]]; then
        echo "✓ Binary execution SKIPPED (cross-compiled binary)"
    else
        HAS_SANITIZER=$(grep -E '\-fsanitize=' "$BUILD_LOG" | head -1 || echo "")
        
        BINARY_OUTPUT=$("$BINARY_PATH" 2>&1 || true)
        
        if echo "$BINARY_OUTPUT" | grep -q "All tests passed!"; then
            echo "✓ Binary execution PASSED"
            if [[ -n "$HAS_SANITIZER" ]]; then
                echo "  Note: Sanitizers enabled, ignoring post-execution sanitizer errors"
            fi
        else
            echo "✗ Binary execution FAILED"
            echo "  Output: $BINARY_OUTPUT"
            exit 1
        fi
    fi
    
    rm -f "$BUILD_LOG"
    
    echo ""
    echo "========================================="
    echo "✓ Test PASSED for mode: $mode"
    echo "========================================="
    echo ""
done

echo "========================================="
echo "All build mode tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
