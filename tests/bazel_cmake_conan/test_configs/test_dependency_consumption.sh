#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONSUMER_DIR="$PROJECT_DIR/consumer"

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

declare -A READELF_MAP=(
    ["linux_x86_64"]="readelf"
    ["linux_arm64"]="readelf"
    ["linux_x86_64_cross_arm64"]="aarch64-linux-gnu-readelf"
    ["linux_arm64_cross_arm64"]="aarch64-linux-gnu-readelf"
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

if [ $# -gt 0 ]; then
    PLATFORM_CONFIGS=("$@")
fi

echo "========================================="
echo "Dependency Consumption Test: bazel_cmake_conan"
echo "========================================="

for config in "${PLATFORM_CONFIGS[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing platform config: $config"
    echo "========================================="

    cd "$CONSUMER_DIR"
    bazel clean

    echo ""
    echo "Building consumer_static with config: $config"
    bazel build //:consumer_static --config=$config --subcommands

    CONSUMER_STATIC_PATH=$(bazel cquery //:consumer_static --output=files --config=$config | head -n1)

    if [ -z "$CONSUMER_STATIC_PATH" ] || [ ! -f "$CONSUMER_STATIC_PATH" ]; then
        echo "✗ consumer_static binary not found"
        exit 1
    fi

    echo ""
    echo "========================================="
    echo "consumer_static Verification"
    echo "========================================="

    READELF_TOOL="${READELF_MAP[$config]}"
    expected_arch="${ARCH_MAP[$config]}"

    BINARY_ARCH=$(file "$CONSUMER_STATIC_PATH" | grep -oE 'x86-64|ARM aarch64' | head -1)
    echo "  Architecture: $BINARY_ARCH"

    if [[ $BINARY_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Static consumer architecture verification PASSED: x86_64"
    elif [[ $BINARY_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Static consumer architecture verification PASSED: aarch64"
    else
        echo "✗ Static consumer architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $BINARY_ARCH"
        exit 1
    fi

    LINKER=$($READELF_TOOL -p .interp "$CONSUMER_STATIC_PATH" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "unknown")
    expected_linker="${DYNAMIC_LINKER_MAP[$config]}"
    if [[ $LINKER == *"$expected_linker"* ]]; then
        echo "✓ Dynamic linker verification PASSED"
    else
        echo "✗ Dynamic linker verification FAILED"
        echo "  Expected: $expected_linker"
        echo "  Found: $LINKER"
        exit 1
    fi

    expected_rpath="${RPATH_MAP[$config]}"
    if [[ -n "$expected_rpath" ]]; then
        RPATH=$($READELF_TOOL -d "$CONSUMER_STATIC_PATH" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' || echo "none")
        if [[ $RPATH == *"$expected_rpath"* ]]; then
            echo "✓ RPATH verification PASSED"
        else
            echo "✗ RPATH verification FAILED"
            echo "  Expected: $expected_rpath"
            echo "  Found: $RPATH"
            exit 1
        fi
    else
        echo "  RPATH verification SKIPPED (not required for this config)"
    fi

    if [[ $config != *"cross"* ]]; then
        BINARY_OUTPUT=$("$CONSUMER_STATIC_PATH" 2>&1)
        if echo "$BINARY_OUTPUT" | grep -q "Consumer dependency test passed!"; then
            echo "✓ Static consumer execution PASSED"
        else
            echo "✗ Static consumer execution FAILED"
            echo "  Output: $BINARY_OUTPUT"
            exit 1
        fi
    else
        echo "✓ Static consumer execution SKIPPED (cross-compiled binary)"
    fi

    echo ""
    echo "Building consumer_shared with config: $config"
    bazel build //:consumer_shared --config=$config

    CONSUMER_SHARED_PATH=$(bazel cquery //:consumer_shared --output=files --config=$config | head -n1)

    if [ -z "$CONSUMER_SHARED_PATH" ] || [ ! -f "$CONSUMER_SHARED_PATH" ]; then
        echo "✗ consumer_shared binary not found"
        exit 1
    fi

    echo ""
    echo "========================================="
    echo "consumer_shared Verification"
    echo "========================================="

    BINARY_ARCH=$(file "$CONSUMER_SHARED_PATH" | grep -oE 'x86-64|ARM aarch64' | head -1)
    echo "  Architecture: $BINARY_ARCH"

    if [[ $BINARY_ARCH == *"x86-64"* ]] && [[ $expected_arch == "x86_64" ]]; then
        echo "✓ Shared consumer architecture verification PASSED: x86_64"
    elif [[ $BINARY_ARCH == *"aarch64"* ]] && [[ $expected_arch == "aarch64" ]]; then
        echo "✓ Shared consumer architecture verification PASSED: aarch64"
    else
        echo "✗ Shared consumer architecture verification FAILED"
        echo "  Expected: $expected_arch"
        echo "  Found: $BINARY_ARCH"
        exit 1
    fi

    if [[ $config != *"cross"* ]]; then
        BINARY_OUTPUT=$("$CONSUMER_SHARED_PATH" 2>&1)
        if echo "$BINARY_OUTPUT" | grep -q "Consumer dependency test passed!"; then
            echo "✓ Shared consumer execution PASSED"
        else
            echo "✗ Shared consumer execution FAILED"
            echo "  Output: $BINARY_OUTPUT"
            exit 1
        fi
    else
        echo "✓ Shared consumer execution SKIPPED (cross-compiled binary)"
    fi

    echo ""
    echo "========================================="
    echo "✓ Dependency consumption test PASSED for config: $config"
    echo "========================================="
done

echo ""
echo "========================================="
echo "All dependency consumption tests PASSED!"
echo "========================================="
