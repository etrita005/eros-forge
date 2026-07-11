#!/bin/bash
# Build-mode test for the bazel_cmake_conan project (cmake_conan_forge).
# cmake_conan_forge strips the release binary (strip_binary=True by default) and
# leaves the debug binary unstripped (strip_binary=False under cmake_debug), so
# build mode is verified via the binary's symbol status plus execution.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIG="${1:-linux_x86_64}"
BUILD_MODES=("debug" "release")

forge_section "Testing Build Modes for Platform: $PLATFORM_CONFIG"

for mode in "${BUILD_MODES[@]}"; do
    forge_section "Testing build mode: $mode (platform: $PLATFORM_CONFIG)"
    forge_load_config "$PLATFORM_CONFIG"

    forge_build "$SRC_DIR" //:hello -- --config="$PLATFORM_CONFIG" --config="$mode" \
        || forge_die "build failed for $mode"

    BINARY=$(forge_find_binary "$SRC_DIR" "hello")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"

    forge_print_binary_info "$BINARY"

    forge_section "Verification: mode=$mode"
    forge_check_arch "$BINARY"
    if [ "$mode" = "release" ]; then
        # cmake_conan_forge strips release binaries (strip_binary=True by default).
        forge_check_symbol_status "$BINARY" "stripped"
    else
        # Debug keeps symbols (strip_binary=False under cmake_debug).
        forge_check_symbol_status "$BINARY" "not stripped"
    fi
    forge_run_binary "$BINARY" "CMake + Conan integration test passed!"

    forge_pass "mode: $mode"
done

echo ""
echo "========================================="
echo "All build mode tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
