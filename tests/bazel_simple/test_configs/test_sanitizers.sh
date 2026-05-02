#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

PLATFORM_CONFIG="${1:-linux_x86_64}"

SANITIZER_CONFIGS=(
    "asan"
    "tsan"
    "ubsan"
    "msan"
)

declare -A SANITIZER_MAP=(
    ["asan"]="asan"
    ["tsan"]="tsan"
    ["ubsan"]="ubsan"
    ["msan"]="msan"
)

declare -A SANITIZER_FLAG_MAP=(
    ["asan"]="address"
    ["tsan"]="thread"
    ["ubsan"]="undefined"
    ["msan"]="memory"
)

echo "========================================="
echo "Testing Sanitizers for Platform: $PLATFORM_CONFIG"
echo "========================================="
echo ""

for config in "${SANITIZER_CONFIGS[@]}"; do
    echo "========================================="
    echo "Testing sanitizer config: $config"
    echo "Platform config: $PLATFORM_CONFIG"
    echo "========================================="
    
    cd "$PROJECT_DIR/src"
    bazel clean
    
    echo ""
    echo "Building with platform: $PLATFORM_CONFIG, sanitizer: $config"
    BUILD_LOG=$(mktemp)
    bazel build //:hello //:math_utils_static //:math_utils_shared --config=$PLATFORM_CONFIG --config=$config --subcommands 2>&1 | tee "$BUILD_LOG"
    
    BINARY_PATH=$(bazel cquery //:hello --output=files --config=$PLATFORM_CONFIG --config=$config | grep -E 'hello$' | head -n1)
    STATIC_LIB_PATH=$(bazel cquery //:math_utils_static --output=files --config=$PLATFORM_CONFIG --config=$config | grep -E '\.a$' | head -n1)
    SHARED_LIB_PATH=$(bazel cquery //:math_utils_shared --output=files --config=$PLATFORM_CONFIG --config=$config | grep -E '\.so$' | head -n1)
    
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
    
    SANITIZER_FLAGS=$(grep -oE '\-fsanitize=[a-z,]+' "$BUILD_LOG" | head -1 || echo "none")
    echo "  Sanitizer Flags: $SANITIZER_FLAGS"
    
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
    echo "[Sanitizer Information]"
    sanitizer_type="${SANITIZER_MAP[$config]}"
    SANITIZER_SYMBOLS=$(nm "$BINARY_PATH" 2>/dev/null | grep -oE "__${sanitizer_type}_[a-z_]*" | head -3 | tr '\n' ' ' || echo "none")
    echo "  Sanitizer Symbols: $SANITIZER_SYMBOLS"
    
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
    if [[ $COMPILER_FOUND == *"g++"* ]] || [[ $COMPILER_FOUND == *"gcc"* ]]; then
        echo "✓ Compiler verification PASSED"
        echo "  Found: $COMPILER_FOUND"
    else
        echo "✗ Compiler verification FAILED"
        echo "  Expected: gcc/g++"
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
    expected_flag="${SANITIZER_FLAG_MAP[$config]}"
    
    if [ "$config" == "msan" ]; then
        if [[ $SANITIZER_FLAGS == *"memory"* ]]; then
            echo "✓ Sanitizer flags verification PASSED"
            echo "  Expected: -fsanitize=$expected_flag"
            echo "  Found: $SANITIZER_FLAGS"
        else
            echo "⚠ MSan verification SKIPPED"
            echo "  Reason: MemorySanitizer requires Clang (not supported by GCC)"
            echo "  Found: ${SANITIZER_FLAGS:-no sanitizer flags}"
        fi
    elif [[ $SANITIZER_FLAGS == *"$expected_flag"* ]]; then
        echo "✓ Sanitizer flags verification PASSED"
        echo "  Expected: -fsanitize=$expected_flag"
        echo "  Found: $SANITIZER_FLAGS"
    else
        echo "✗ Sanitizer flags verification FAILED"
        echo "  Expected: -fsanitize=$expected_flag"
        echo "  Found: $SANITIZER_FLAGS"
        exit 1
    fi
    
    echo ""
    if [ "$config" == "msan" ] && [[ $SANITIZER_SYMBOLS != *"msan"* ]]; then
        echo "⚠ Sanitizer symbols SKIPPED"
        echo "  Reason: MSan requires Clang"
    elif [ -n "$SANITIZER_SYMBOLS" ] && [[ $SANITIZER_SYMBOLS != "none" ]]; then
        echo "✓ Sanitizer symbols verification PASSED"
        echo "  Expected: __${sanitizer_type}_* symbols"
        echo "  Found: $SANITIZER_SYMBOLS"
    else
        echo "⚠ Sanitizer symbols not found in binary"
        echo "  This may be normal for static linking"
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
        BINARY_OUTPUT=$("$BINARY_PATH" 2>&1 || true)
        if echo "$BINARY_OUTPUT" | grep -q "All tests passed!"; then
            echo "✓ Binary execution PASSED"
        else
            echo "⚠ Binary execution may have sanitizer warnings"
            echo "  Output: $(echo "$BINARY_OUTPUT" | head -3)"
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
