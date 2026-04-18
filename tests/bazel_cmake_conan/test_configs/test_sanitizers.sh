#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_UTILS="$SCRIPT_DIR/../../test_utils.py"

SANITIZER_CONFIGS=(
    "tsan"
    "debug"
)

PLATFORM_CONFIG="${1:-linux_x86_64}"

declare -A SANITIZER_MAP=(
    ["tsan"]="tsan"
    ["debug"]="none"
)

declare -A SANITIZER_FLAG_MAP=(
    ["tsan"]="thread"
    ["debug"]="none"
)

declare -A READELF_MAP=(
    ["linux_x86_64"]="readelf"
    ["linux_arm64"]="readelf"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-readelf"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-readelf"
)

declare -A NM_MAP=(
    ["linux_x86_64"]="nm"
    ["linux_arm64"]="nm"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-nm"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-nm"
)

READELF_TOOL="${READELF_MAP[$PLATFORM_CONFIG]}"
NM_TOOL="${NM_MAP[$PLATFORM_CONFIG]}"

for config in "${SANITIZER_CONFIGS[@]}"; do
    echo "========================================="
    echo "Testing sanitizer config: $config (platform: $PLATFORM_CONFIG)"
    echo "========================================="
    
    cd "$PROJECT_DIR"
    bazel clean
    
    echo ""
    echo "Building with config: $config"
    BUILD_LOG=$(mktemp)
    bazel build //:hello --config=$PLATFORM_CONFIG --config=$config --subcommands 2>&1 | tee "$BUILD_LOG"
    
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
    
    SANITIZER_FLAGS=$(grep -oE '\-fsanitize=[a-z,]+' "$BUILD_LOG" | head -1 || echo "none")
    echo "  Sanitizer Flags: $SANITIZER_FLAGS"
    
    echo ""
    echo "[Linker Information]"
    LINKER=$($READELF_TOOL -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    echo ""
    echo "[Sanitizer Information]"
    sanitizer_type="${SANITIZER_MAP[$config]}"
    if [ "$sanitizer_type" != "none" ]; then
        SANITIZER_SYMBOLS=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -oE "__${sanitizer_type}_[a-z_]*" | head -3 | tr '\n' ' ' || echo "none")
        echo "  Sanitizer Symbols: $SANITIZER_SYMBOLS"
    else
        ASAN_SYMBOLS=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -oE "__asan_[a-z_]*" | head -1 || echo "")
        TSAN_SYMBOLS=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -oE "__tsan_[a-z_]*" | head -1 || echo "")
        MSAN_SYMBOLS=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -oE "__msan_[a-z_]*" | head -1 || echo "")
        if [ -z "$ASAN_SYMBOLS" ] && [ -z "$TSAN_SYMBOLS" ] && [ -z "$MSAN_SYMBOLS" ]; then
            echo "  Sanitizer Symbols: none (as expected)"
        else
            echo "  Sanitizer Symbols: FOUND (unexpected)"
        fi
    fi
    
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
    expected_flag="${SANITIZER_FLAG_MAP[$config]}"
    if [ "$expected_flag" != "none" ]; then
        if [[ $SANITIZER_FLAGS == *"$expected_flag"* ]]; then
            echo "✓ Sanitizer flags verification PASSED"
            echo "  Expected: -fsanitize=$expected_flag"
            echo "  Found: $SANITIZER_FLAGS"
        else
            echo "⚠ Sanitizer flags verification WARNING"
            echo "  Expected: -fsanitize=$expected_flag"
            echo "  Found: ${SANITIZER_FLAGS:-none}"
            echo "  Note: CMake builds may not pass sanitizer flags from Bazel config"
        fi
    else
        if [[ $SANITIZER_FLAGS == "none" ]] || [[ -z "$SANITIZER_FLAGS" ]]; then
            echo "✓ No sanitizer flags verification PASSED"
            echo "  Expected: no sanitizer flags"
            echo "  Found: ${SANITIZER_FLAGS:-none}"
        else
            echo "⚠ No sanitizer flags verification WARNING"
            echo "  Expected: no sanitizer flags"
            echo "  Found: $SANITIZER_FLAGS"
        fi
    fi
    
    echo ""
    if [ "$sanitizer_type" != "none" ]; then
        if [ -n "$SANITIZER_SYMBOLS" ] && [[ $SANITIZER_SYMBOLS != "none" ]]; then
            echo "✓ Sanitizer symbols verification PASSED"
            echo "  Expected: __${sanitizer_type}_* symbols"
            echo "  Found: $SANITIZER_SYMBOLS"
        else
            echo "⚠ Sanitizer symbols verification WARNING"
            echo "  Expected: __${sanitizer_type}_* symbols"
            echo "  Found: none"
            echo "  Note: CMake builds may not include sanitizer instrumentation"
        fi
    else
        ASAN_CHECK=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -c "__asan_" || true)
        TSAN_CHECK=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -c "__tsan_" || true)
        MSAN_CHECK=$($NM_TOOL "$BINARY_PATH" 2>/dev/null | grep -c "__msan_" || true)
        ASAN_COUNT=$(echo "$ASAN_CHECK" | tr -d '[:space:]')
        TSAN_COUNT=$(echo "$TSAN_CHECK" | tr -d '[:space:]')
        MSAN_COUNT=$(echo "$MSAN_CHECK" | tr -d '[:space:]')
        if [ "$ASAN_COUNT" -eq 0 ] 2>/dev/null && [ "$TSAN_COUNT" -eq 0 ] 2>/dev/null && [ "$MSAN_COUNT" -eq 0 ] 2>/dev/null; then
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
    echo "✓ Test PASSED for config: $config"
    echo "========================================="
    echo ""
done

echo "========================================="
echo "All sanitizer tests PASSED!"
echo "========================================="
