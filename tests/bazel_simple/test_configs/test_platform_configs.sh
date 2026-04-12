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
    ["linux_x86_64"]="/lib64/ld-linux-x86-64.so.2"
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

declare -A OBJDUMP_MAP=(
    ["linux_x86_64"]="objdump"
    ["linux_arm64"]="objdump"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-objdump"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-objdump"
)

declare -A NM_MAP=(
    ["linux_x86_64"]="nm"
    ["linux_arm64"]="nm"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-nm"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-nm"
)

declare -A READELF_MAP=(
    ["linux_x86_64"]="readelf"
    ["linux_arm64"]="readelf"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-readelf"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-readelf"
)

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
    bazel build //:hello //:math_utils_static //:math_utils_shared --config=$config --subcommands 2>&1 | tee "$BUILD_LOG"
    
    BINARY_PATH=$(bazel cquery //:hello --output=files --config=$config | grep -E 'hello$' | head -n1)
    STATIC_LIB_PATH=$(bazel cquery //:math_utils_static --output=files --config=$config | grep -E '\.a$' | head -n1)
    SHARED_LIB_PATH=$(bazel cquery //:math_utils_shared --output=files --config=$config | grep -E '\.so$' | head -n1)
    
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
    
    OPT_LEVEL=$(grep -oE '\-O[0-3sg]' "$BUILD_LOG" | head -1 || echo "unknown")
    echo "  Optimization: $OPT_LEVEL"
    
    DEFINES=$(grep -oE '\-D[A-Z_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
    echo "  Defines: $DEFINES"
    
    WARNINGS=$(grep -oE '\-W[a-zA-Z0-9_-]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
    echo "  Warnings: $WARNINGS"
    
    echo ""
    echo "[Linker Flags from Build Log]"
    PARAMS_FILE=$(grep -oE 'bazel-out/[a-zA-Z0-9_/.-]+\.params' "$BUILD_LOG" | grep hello | head -1 || echo "")
    if [ -n "$PARAMS_FILE" ] && [ -f "$PARAMS_FILE" ]; then
        DYNAMIC_LINKER_FLAG=$(grep -E '\-\-dynamic-linker=' "$PARAMS_FILE" | head -1 || echo "")
        echo "  Dynamic Linker Flag: $DYNAMIC_LINKER_FLAG"
        
        RPATH_FLAG=$(grep -E '\-\-rpath=' "$PARAMS_FILE" | head -1 || echo "")
        echo "  RPATH Flag: $RPATH_FLAG"
        
        LIBS=$(grep -E '^\-l' "$PARAMS_FILE" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Libraries: $LIBS"
    else
        DYNAMIC_LINKER_FLAG=$(grep -oE '\-\-dynamic-linker=[^ ]+' "$BUILD_LOG" | head -1 || echo "")
        echo "  Dynamic Linker Flag: $DYNAMIC_LINKER_FLAG"
        
        RPATH_FLAG=$(grep -oE '\-Wl,-rpath[^ ]*|\-\-rpath=[^ ]+' "$BUILD_LOG" | head -1 || echo "")
        echo "  RPATH Flag: $RPATH_FLAG"
        
        LIBS=$(grep -oE '\-l[a-zA-Z0-9_]+' "$BUILD_LOG" | sort -u | head -5 | tr '\n' ' ' || echo "none")
        echo "  Libraries: $LIBS"
    fi
    
    echo ""
    echo "========================================="
    echo "Binary (hello) Verification"
    echo "========================================="
    
    OBJDUMP_TOOL="${OBJDUMP_MAP[$config]}"
    NM_TOOL="${NM_MAP[$config]}"
    READELF_TOOL="${READELF_MAP[$config]}"
    
    echo ""
    echo "[Linker Information]"
    LINKER=$($READELF_TOOL -p .interp "$BINARY_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    echo "  Dynamic Linker: $LINKER"
    
    RPATH=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
    echo "  RPATH/RUNPATH: $RPATH"
    
    NEEDED_LIBS=$($READELF_TOOL -d "$BINARY_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
    echo "  Needed Libraries: $NEEDED_LIBS"
    
    echo ""
    echo "[Binary Architecture]"
    BINARY_ARCH=$(file "$BINARY_PATH" | grep -oE 'x86-64|ARM aarch64' | head -1)
    echo "  Architecture: $BINARY_ARCH"
    
    echo ""
    echo "========================================="
    echo "Static Library (libmath_utils_static.a) Verification"
    echo "========================================="
    
    echo ""
    if [ -f "$STATIC_LIB_PATH" ]; then
        echo "  Path: $STATIC_LIB_PATH"
        STATIC_LIB_SIZE=$(stat -c%s "$STATIC_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $STATIC_LIB_SIZE bytes"
        STATIC_LIB_SYMBOLS=$($NM_TOOL "$STATIC_LIB_PATH" 2>/dev/null | grep -E 'T.*calculate_sum|T.*get_greeting|T.*fibonacci' | wc -l || echo "0")
        echo "  Exported Symbols: $STATIC_LIB_SYMBOLS (calculate_sum, get_greeting, fibonacci)"
        STATIC_LIB_ARCH=$($OBJDUMP_TOOL -f "$STATIC_LIB_PATH" 2>/dev/null | grep "architecture:" | grep -oE 'x86-64|aarch64' | head -1 || echo "unknown")
        echo "  Architecture: $STATIC_LIB_ARCH"
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
        SHARED_LIB_SIZE=$(stat -c%s "$SHARED_LIB_PATH" 2>/dev/null || echo "unknown")
        echo "  Size: $SHARED_LIB_SIZE bytes"
        SHARED_LIB_SYMBOLS=$($NM_TOOL -D "$SHARED_LIB_PATH" 2>/dev/null | grep -E 'T.*calculate_sum|T.*get_greeting|T.*fibonacci' | wc -l || echo "0")
        echo "  Exported Symbols: $SHARED_LIB_SYMBOLS (calculate_sum, get_greeting, fibonacci)"
        SHARED_LIB_ARCH=$(file "$SHARED_LIB_PATH" | grep -oE 'x86-64|ARM aarch64' | head -1 || echo "unknown")
        echo "  Architecture: $SHARED_LIB_ARCH"
        SO_NEEDED=$($READELF_TOOL -d "$SHARED_LIB_PATH" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ' || echo "none")
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
        
        echo ""
        echo "Cross-compilation link flags verification:"
        if [[ $DYNAMIC_LINKER_FLAG == *"/opt/eros/lib/ld-linux-aarch64.so.1"* ]]; then
            echo "✓ Dynamic linker flag in build log PASSED"
            echo "  Found: $DYNAMIC_LINKER_FLAG"
        else
            echo "✗ Dynamic linker flag in build log FAILED"
            echo "  Expected: --dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1"
            echo "  Found: $DYNAMIC_LINKER_FLAG"
            exit 1
        fi
        
        echo ""
        if [[ $RPATH_FLAG == *"/opt/eros/lib"* ]]; then
            echo "✓ RPATH flag in build log PASSED"
            echo "  Found: $RPATH_FLAG"
        else
            echo "✗ RPATH flag in build log FAILED"
            echo "  Expected: --rpath=/opt/eros/lib"
            echo "  Found: $RPATH_FLAG"
            exit 1
        fi
    else
        echo "  RPATH verification SKIPPED (not required for this config)"
    fi
    
    echo ""
    expected_arch="${ARCH_MAP[$config]}"
    if [[ $BINARY_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Binary architecture verification PASSED: x86_64"
    elif [[ $BINARY_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Binary architecture verification PASSED: aarch64"
    else
        echo "✗ Binary architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $BINARY_ARCH"
        exit 1
    fi
    
    echo ""
    if [[ $STATIC_LIB_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Static library architecture verification PASSED: x86_64"
    elif [[ $STATIC_LIB_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Static library architecture verification PASSED: aarch64"
    else
        echo "✗ Static library architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $STATIC_LIB_ARCH"
        exit 1
    fi
    
    echo ""
    if [[ $SHARED_LIB_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Shared library architecture verification PASSED: x86_64"
    elif [[ $SHARED_LIB_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Shared library architecture verification PASSED: aarch64"
    else
        echo "✗ Shared library architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $SHARED_LIB_ARCH"
        exit 1
    fi
    
    echo ""
    if [ "$STATIC_LIB_SYMBOLS" -ge 3 ]; then
        echo "✓ Static library symbols verification PASSED"
        echo "  Found $STATIC_LIB_SYMBOLS exported symbols"
    else
        echo "✗ Static library symbols verification FAILED"
        echo "  Expected: 3 or more exported symbols"
        echo "  Found: $STATIC_LIB_SYMBOLS"
        exit 1
    fi
    
    echo ""
    if [ "$SHARED_LIB_SYMBOLS" -ge 3 ]; then
        echo "✓ Shared library symbols verification PASSED"
        echo "  Found $SHARED_LIB_SYMBOLS exported symbols"
    else
        echo "✗ Shared library symbols verification FAILED"
        echo "  Expected: 3 or more exported symbols"
        echo "  Found: $SHARED_LIB_SYMBOLS"
        exit 1
    fi
    
    echo ""
    if [[ $config != *"cross"* ]]; then
        BINARY_OUTPUT=$("$BINARY_PATH" 2>&1 || true)
        if echo "$BINARY_OUTPUT" | grep -q "All tests passed!"; then
            echo "✓ Binary execution PASSED"
        else
            echo "✗ Binary execution FAILED"
            echo "  Output: $BINARY_OUTPUT"
            exit 1
        fi
    else
        echo "✓ Binary execution SKIPPED (cross-compiled binary)"
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
