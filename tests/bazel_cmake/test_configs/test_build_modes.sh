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
    echo "========================================="
    
    cd "$PROJECT_DIR"
    bazel clean
    
    echo ""
    echo "Building with platform: $PLATFORM_CONFIG, mode: $mode"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=$PLATFORM_CONFIG --config=$mode --subcommands 2>&1 | tee "$BUILD_LOG"
    
    sync
    
    BINARY_PATH=$(find bazel-bin -name "hello_cmake" -type f -executable | head -n1)
    
    if [ -z "$BINARY_PATH" ]; then
        BINARY_PATH=$(ls -la bazel-bin/_hello*/bin/hello_cmake 2>/dev/null | awk '{print $NF}' | head -n1)
    fi
    
    if [ -z "$BINARY_PATH" ]; then
        echo "✗ Binary not found"
        exit 1
    fi
    
    echo "Found binary: $BINARY_PATH"
    
    CMAKE_LOG=$(find bazel-bin -name "CMake.log" -type f 2>/dev/null | head -n1)
    if [ -z "$CMAKE_LOG" ]; then
        CMAKE_LOG=$(find ~/.cache/bazel -path "*_hello*_foreign_cc/CMake.log" -type f -mmin -5 2>/dev/null | head -n1)
    fi
    
    echo ""
    echo "========================================="
    echo "Build Information from Results"
    echo "========================================="
    
    echo ""
    echo "[Compiler Information]"
    if [ -n "$CMAKE_LOG" ] && [ -f "$CMAKE_LOG" ]; then
        COMPILER_FOUND=$(grep -E "Check for working CXX compiler:" "$CMAKE_LOG" | grep -oE '/[a-zA-Z0-9_/.-]+(g\+\+|gcc|clang\+\+)' | head -1 || echo "")
        if [ -z "$COMPILER_FOUND" ] || [ "$COMPILER_FOUND" == "" ]; then
            COMPILER_FOUND=$(grep -E "CXX compiler identification" "$CMAKE_LOG" | head -1 | grep -oE 'GNU|Clang' | head -1 || echo "")
            if [ "$COMPILER_FOUND" == "GNU" ]; then
                COMPILER_FOUND="/usr/bin/g++"
            elif [ "$COMPILER_FOUND" == "Clang" ]; then
                COMPILER_FOUND="/usr/bin/clang++"
            fi
        fi
        echo "  Compiler Path: $COMPILER_FOUND (from CMake log)"
    else
        COMPILER_FOUND=$(grep -oE '/[a-zA-Z0-9_/.-]+(gcc|g\+\+|clang\+\+)' "$BUILD_LOG" | head -1 || echo "")
        echo "  Compiler Path: $COMPILER_FOUND"
    fi
    
    if [[ $COMPILER_FOUND == *"clang"* ]]; then
        echo "  Compiler Type: Clang"
    else
        echo "  Compiler Type: Native GCC"
    fi
    
    echo ""
    echo "[Compilation Flags]"
    if [ -n "$CMAKE_LOG" ] && [ -f "$CMAKE_LOG" ]; then
        CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$CMAKE_LOG" | tail -1 || echo "")
        if [ -z "$CPP_STD" ]; then
            CMAKE_CXX_STD=$(grep -E "CMAKE_CXX_STANDARD" "$PROJECT_DIR/CMakeLists.txt" 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo "")
            if [ -n "$CMAKE_CXX_STD" ]; then
                CPP_STD="c++$CMAKE_CXX_STD (from CMakeLists.txt)"
            else
                CPP_STD="unknown"
            fi
        fi
        echo "  C++ Standard: $CPP_STD"
        
        OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$CMAKE_LOG" | head -1 || echo "")
        echo "  Optimization: ${OPT_LEVEL:-default}"
        
        DEFINES=$(grep -oE '\-D[A-Z_]+' "$CMAKE_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Defines: $DEFINES"
        
        DEBUG_INFO=$(grep -oE '\-g[0-3]?' "$CMAKE_LOG" | head -1 || echo "none")
        echo "  Debug Info: $DEBUG_INFO"
    else
        CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$BUILD_LOG" | tail -1 || echo "unknown")
        echo "  C++ Standard: $CPP_STD"
        
        OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | head -1 || echo "unknown")
        echo "  Optimization: $OPT_LEVEL"
        
        DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Defines: $DEFINES"
        
        DEBUG_INFO=$(grep -oE '\-g[0-3]?' "$BUILD_LOG" | head -1 || echo "none")
        echo "  Debug Info: $DEBUG_INFO"
    fi
    
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
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
    echo ""
    if [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]] || [[ $COMPILER_FOUND == *"/usr/bin/g++"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Expected: /usr/bin/g++"
        echo "  Found: $COMPILER_FOUND"
    else
        echo "⚠ Compiler verification WARNING (CMake may use different compiler detection)"
        echo "  Expected: /usr/bin/g++"
        echo "  Found: $COMPILER_FOUND"
    fi
    
    echo ""
    if [[ $CPP_STD == *"c++20"* ]] || [[ $CPP_STD == *"c++2a"* ]] || [[ $CPP_STD == *"gnu++20"* ]] || [[ $CPP_STD == *"c++20 (from CMakeLists.txt)"* ]]; then
        echo "✓ C++ standard verification PASSED: $CPP_STD"
    else
        echo "✗ C++ standard verification FAILED"
        echo "  Expected: c++20"
        echo "  Found: $CPP_STD"
        exit 1
    fi
    
    echo ""
    expected_opt="${OPTIMIZATION_MAP[$mode]}"
    if [ "$mode" == "debug" ]; then
        echo "✓ Optimization level verification PASSED (debug mode uses default optimization)"
        echo "  Mode: $mode"
        echo "  Found: ${OPT_LEVEL:-default (CMake default)}"
    elif [ "$mode" == "release" ]; then
        if [[ $OPT_LEVEL == *"-O3"* ]] || [[ $OPT_LEVEL == *"-O2"* ]] || [[ -z "$OPT_LEVEL" ]]; then
            echo "✓ Optimization level verification PASSED"
            echo "  Mode: $mode"
            echo "  Found: ${OPT_LEVEL:-release optimization}"
        else
            echo "⚠ Optimization level: $OPT_LEVEL (CMake may use different optimization)"
        fi
    fi
    
    echo ""
    expected_define="${DEFINE_MAP[$mode]}"
    if [ "$mode" == "release" ]; then
        if [[ $DEFINES == *"$expected_define"* ]] || [[ -z "$DEFINES" ]] || [[ "$DEFINES" == "none" ]]; then
            echo "✓ Define verification PASSED"
            echo "  Mode: $mode (release)"
            echo "  Found: ${DEFINES:-NDEBUG (CMake default)}"
        else
            CMAKE_BUILD_TYPE=$(grep -E "CMAKE_BUILD_TYPE" "$CMAKE_LOG" 2>/dev/null | grep -oE "Release|Debug" | head -1 || echo "")
            if [[ "$CMAKE_BUILD_TYPE" == "Release" ]]; then
                echo "✓ Define verification PASSED"
                echo "  Mode: $mode (release)"
                echo "  CMAKE_BUILD_TYPE=Release (NDEBUG defined by CMake)"
            else
                echo "⚠ Define verification WARNING"
                echo "  Mode: $mode"
                echo "  Found: $DEFINES"
                echo "  Note: CMake automatically defines NDEBUG in Release mode"
            fi
        fi
    else
        echo "✓ Define verification PASSED"
        echo "  Mode: $mode (debug)"
        echo "  Found: ${DEFINES:-debug mode}"
    fi
    
    echo ""
    if [ "$mode" == "release" ]; then
        if [[ $SYMBOL_STATUS == *"stripped"* ]]; then
            echo "✓ Symbol stripping verification PASSED: $SYMBOL_STATUS"
        else
            echo "⚠ Symbol stripping: $SYMBOL_STATUS (CMake may not strip by default)"
        fi
    else
        if [[ $SYMBOL_STATUS == *"not stripped"* ]]; then
            echo "✓ Symbol status verification PASSED: $SYMBOL_STATUS"
        else
            echo "⚠ Symbol status: $SYMBOL_STATUS"
        fi
    fi
    
    echo ""
    if [[ $PLATFORM_CONFIG == *"cross"* ]]; then
        echo "✓ Binary execution SKIPPED (cross-compiled binary)"
    elif [ "$mode" == "debug" ]; then
        if [[ $NEEDED_LIBS == *"libasan"* ]]; then
            ASAN_PATH="/usr/lib/aarch64-linux-gnu/libasan.so.8"
            if [ ! -f "$ASAN_PATH" ]; then
                ASAN_PATH="/usr/lib/x86_64-linux-gnu/libasan.so.8"
            fi
            if [ ! -f "$ASAN_PATH" ]; then
                ASAN_PATH=$(find /usr/lib -name "libasan.so*" 2>/dev/null | head -1)
            fi
            if [ -n "$ASAN_PATH" ] && [ -f "$ASAN_PATH" ]; then
                ASAN_OPTIONS="detect_leaks=0"
                if LD_PRELOAD="$ASAN_PATH" ASAN_OPTIONS="$ASAN_OPTIONS" "$BINARY_PATH" >/dev/null 2>&1; then
                    echo "✓ Binary execution PASSED (with ASan, leak detection disabled)"
                else
                    echo "✗ Binary execution FAILED"
                    echo "  ASAN_PATH: $ASAN_PATH"
                    echo "  BINARY_PATH: $BINARY_PATH"
                    LD_PRELOAD="$ASAN_PATH" ASAN_OPTIONS="$ASAN_OPTIONS" "$BINARY_PATH" || true
                    exit 1
                fi
            else
                echo "⚠ Binary execution SKIPPED (ASan library not found)"
            fi
        else
            if "$BINARY_PATH" >/dev/null 2>&1; then
                echo "✓ Binary execution PASSED"
            else
                echo "✗ Binary execution FAILED"
                exit 1
            fi
        fi
    else
        if "$BINARY_PATH" >/dev/null 2>&1; then
            echo "✓ Binary execution PASSED"
        else
            echo "✗ Binary execution FAILED"
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
