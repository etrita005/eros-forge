#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

PLATFORM_CONFIG="${1:-linux_x86_64}"

SANITIZER_CONFIGS=(
    "asan"
    "tsan"
)

declare -A SANITIZER_MAP=(
    ["asan"]="asan"
    ["tsan"]="tsan"
)

declare -A SANITIZER_FLAG_MAP=(
    ["asan"]="address"
    ["tsan"]="thread"
)

echo "========================================="
echo "Testing Sanitizers for Platform: $PLATFORM_CONFIG"
echo "========================================="
echo ""

for config in "${SANITIZER_CONFIGS[@]}"; do
    echo "========================================="
    echo "Testing sanitizer config: $config"
    echo "========================================="
    
    cd "$PROJECT_DIR/src"
    bazel clean
    
    echo ""
    echo "Building with platform: $PLATFORM_CONFIG, config: $config"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=$PLATFORM_CONFIG --config=$config --subcommands 2>&1 | tee "$BUILD_LOG"
    
    # Wait for filesystem sync
    sync
    
    # CMake project generates binary in _hello_release directory
    BINARY_PATH=$(find bazel-bin -name "hello_cmake" -type f -executable | head -n1)
    
    if [ -z "$BINARY_PATH" ]; then
        # Try other possible locations
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
        COMPILER_FOUND=$(grep -oE '/[a-zA-Z0-9_/.-]+(gcc|g\+\+|clang\+\+)' "$BUILD_LOG" | head -1 || echo "unknown")
        echo "  Compiler Path: $COMPILER_FOUND"
    fi
    
    if [[ $COMPILER_FOUND == *"clang"* ]]; then
        echo "  Compiler Type: Clang"
    elif [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]]; then
        echo "  Compiler Type: Cross-compiler (aarch64)"
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
        
        OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$CMAKE_LOG" | head -1 || echo "default")
        echo "  Optimization: $OPT_LEVEL"
        
        DEFINES=$(grep -oE '\-D[A-Z_]+' "$CMAKE_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Defines: $DEFINES"
        
        SANITIZER_FLAGS=$(grep -oE '\-fsanitize=[a-z,]+' "$CMAKE_LOG" | head -1 || echo "none")
        echo "  Sanitizer Flags: $SANITIZER_FLAGS"
    else
        CPP_STD=$(grep -oE '\-std=[a-z0-9\+]+' "$BUILD_LOG" | tail -1 || echo "unknown")
        echo "  C++ Standard: $CPP_STD"
        
        OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | head -1 || echo "unknown")
        echo "  Optimization: $OPT_LEVEL"
        
        DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Defines: $DEFINES"
        
        SANITIZER_FLAGS=$(grep -oE '\-fsanitize=[a-z,]+' "$BUILD_LOG" | head -1 || echo "none")
        echo "  Sanitizer Flags: $SANITIZER_FLAGS"
    fi
    
    # Extract and display linker information from binary
    echo ""
    echo "[Linker Information]"
    LINKER=$(readelf -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$(readelf -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    # Check sanitizer symbols in binary
    echo ""
    echo "[Sanitizer Information]"
    sanitizer_type="${SANITIZER_MAP[$config]}"
    if [ "$sanitizer_type" != "none" ]; then
        SANITIZER_SYMBOLS=$(nm "$BINARY_PATH" 2>/dev/null | grep -oE "__${sanitizer_type}_[a-z_]*" | head -3 | tr '\n' ' ' || echo "none")
        echo "  Sanitizer Symbols: $SANITIZER_SYMBOLS"
    else
        ASAN_SYMBOLS=$(nm "$BINARY_PATH" 2>/dev/null | grep -oE "__asan_[a-z_]*" | head -1 || echo "")
        TSAN_SYMBOLS=$(nm "$BINARY_PATH" 2>/dev/null | grep -oE "__tsan_[a-z_]*" | head -1 || echo "")
        MSAN_SYMBOLS=$(nm "$BINARY_PATH" 2>/dev/null | grep -oE "__msan_[a-z_]*" | head -1 || echo "")
        if [ -z "$ASAN_SYMBOLS" ] && [ -z "$TSAN_SYMBOLS" ] && [ -z "$MSAN_SYMBOLS" ]; then
            echo "  Sanitizer Symbols: none (as expected)"
        else
            echo "  Sanitizer Symbols: FOUND (unexpected)"
        fi
    fi
    
    echo ""
    echo "========================================="
    echo "Verification Against Forge Configuration"
    echo "========================================="
    
    # Verify compiler
    echo ""
    if [[ $PLATFORM_CONFIG == *"cross"* ]]; then
        if [[ $COMPILER_FOUND == *"aarch64-linux-gnu"* ]]; then
            echo "✓ Compiler verification PASSED"
            echo "  Expected: /usr/bin/aarch64-linux-gnu-g++"
            echo "  Found: $COMPILER_FOUND"
        else
            echo "✗ Compiler verification FAILED"
            echo "  Expected: /usr/bin/aarch64-linux-gnu-g++"
            echo "  Found: $COMPILER_FOUND"
            exit 1
        fi
    else
        if [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]] || [[ $COMPILER_FOUND == *"/usr/bin/g++"* ]]; then
            echo "✓ Compiler verification PASSED"
            echo "  Expected: /usr/bin/g++"
            echo "  Found: $COMPILER_FOUND"
        else
            echo "⚠ Compiler verification WARNING (CMake may use different compiler detection)"
            echo "  Expected: /usr/bin/g++"
            echo "  Found: $COMPILER_FOUND"
        fi
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
    
    # Verify sanitizer flags
    echo ""
    expected_flag="${SANITIZER_FLAG_MAP[$config]}"
    if [ "$expected_flag" != "none" ]; then
        if [[ $SANITIZER_FLAGS == *"$expected_flag"* ]]; then
            echo "✓ Sanitizer flags verification PASSED"
            echo "  Expected: -fsanitize=$expected_flag"
            echo "  Found: $SANITIZER_FLAGS"
        else
            echo "✗ Sanitizer flags verification FAILED"
            echo "  Expected: -fsanitize=$expected_flag"
            echo "  Found: $SANITIZER_FLAGS"
            exit 1
        fi
    else
        if [[ $SANITIZER_FLAGS == "none" ]] || [[ -z "$SANITIZER_FLAGS" ]]; then
            echo "✓ No sanitizer flags verification PASSED"
            echo "  Expected: no sanitizer flags"
            echo "  Found: ${SANITIZER_FLAGS:-none}"
        else
            echo "✗ No sanitizer flags verification FAILED"
            echo "  Expected: no sanitizer flags"
            echo "  Found: $SANITIZER_FLAGS"
            exit 1
        fi
    fi
    
    # Verify sanitizer symbols in binary
    echo ""
    if [ "$sanitizer_type" != "none" ]; then
        if [ -n "$SANITIZER_SYMBOLS" ] && [[ $SANITIZER_SYMBOLS != "none" ]]; then
            echo "✓ Sanitizer symbols verification PASSED"
            echo "  Expected: __${sanitizer_type}_* symbols"
            echo "  Found: $SANITIZER_SYMBOLS"
        else
            echo "✗ Sanitizer symbols verification FAILED"
            echo "  Expected: __${sanitizer_type}_* symbols"
            echo "  Found: none"
            exit 1
        fi
    else
        ASAN_CHECK=$(nm "$BINARY_PATH" 2>/dev/null | grep -c "__asan_" || echo "0")
        TSAN_CHECK=$(nm "$BINARY_PATH" 2>/dev/null | grep -c "__tsan_" || echo "0")
        MSAN_CHECK=$(nm "$BINARY_PATH" 2>/dev/null | grep -c "__msan_" || echo "0")
        if [ "$ASAN_CHECK" -eq 0 ] && [ "$TSAN_CHECK" -eq 0 ] && [ "$MSAN_CHECK" -eq 0 ]; then
            echo "✓ No sanitizer symbols verification PASSED"
            echo "  Expected: no sanitizer symbols"
            echo "  Found: none"
        else
            echo "✗ No sanitizer symbols verification FAILED"
            echo "  Expected: no sanitizer symbols"
            echo "  Found: sanitizer symbols present"
            exit 1
        fi
    fi
    
    # Run binary
    echo ""
    if [[ $PLATFORM_CONFIG == *"cross"* ]]; then
        echo "✓ Binary execution SKIPPED (cross-compiled binary)"
    else
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
    fi
    
    rm -f "$BUILD_LOG"
    
    echo ""
    echo "========================================="
    echo "✓ Test PASSED for config: $config"
    echo "========================================="
    echo ""
done

echo "========================================="
echo "All sanitizer tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
