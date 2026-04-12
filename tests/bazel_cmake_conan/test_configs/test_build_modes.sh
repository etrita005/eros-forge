#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

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

for mode in "${BUILD_MODES[@]}"; do
    echo "========================================="
    echo "Testing build mode: $mode"
    echo "========================================="
    
    cd "$PROJECT_DIR"
    bazel clean
    
    echo ""
    echo "Building with mode: $mode"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=linux_x86_64 --config=$mode --subcommands 2>&1 | tee "$BUILD_LOG"
    
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
    COMPILER_FOUND=$(grep -oE '/[a-zA-Z0-9_/.-]+(gcc|g\+\+|clang\+\+)' "$BUILD_LOG" | head -1 || echo "unknown")
    echo "  Compiler Path: $COMPILER_FOUND"
    if [[ $COMPILER_FOUND == *"clang"* ]]; then
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
    
    DEBUG_INFO=$(grep -oE '\-g[0-3]?' "$BUILD_LOG" | head -1 || echo "none")
    echo "  Debug Info: $DEBUG_INFO"
    
    # Extract and display linker information from binary
    echo ""
    echo "[Linker Information]"
    LINKER=$(readelf -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    # Check symbols
    echo ""
    echo "[Symbol Information]"
    SYMBOL_STATUS=$(file "$BINARY_PATH" | grep -oE 'stripped|not stripped' || echo "unknown")
    echo "  Symbol Status: $SYMBOL_STATUS"
    
    echo ""
    echo "========================================="
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
    # Verify compiler
    echo ""
    if [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Expected: /usr/bin/g++"
        echo "  Found: $COMPILER_FOUND"
    else
        echo "✗ Compiler verification FAILED"
        echo "  Expected: /usr/bin/g++"
        echo "  Found: $COMPILER_FOUND"
        exit 1
    fi
    
    # Verify C++ standard
    echo ""
    if [[ $CPP_STD == *"c++20"* ]] || [[ $CPP_STD == *"gnu++20"* ]]; then
        echo "✓ C++ standard verification PASSED: $CPP_STD"
    else
        echo "✗ C++ standard verification FAILED"
        echo "  Expected: c++20"
        echo "  Found: $CPP_STD"
        exit 1
    fi
    
    # Verify optimization level
    echo ""
    expected_opt="${OPTIMIZATION_MAP[$mode]}"
    if [[ $OPT_LEVEL == *"$expected_opt"* ]] || [[ -z "$OPT_LEVEL" && $mode == "debug" ]]; then
        echo "✓ Optimization level verification PASSED"
        echo "  Expected: $expected_opt"
        echo "  Found: ${OPT_LEVEL:-not specified (default -O0)}"
    else
        echo "✗ Optimization level verification FAILED"
        echo "  Expected: $expected_opt"
        echo "  Found: $OPT_LEVEL"
        exit 1
    fi
    
    # Verify defines
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
    
    # Verify symbol status for release mode
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
    
    # Run binary
    echo ""
    if "$BINARY_PATH" >/dev/null 2>&1; then
        echo "✓ Binary execution PASSED"
    else
        echo "✗ Binary execution FAILED"
        exit 1
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
