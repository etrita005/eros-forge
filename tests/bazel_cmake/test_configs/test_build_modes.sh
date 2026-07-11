#!/bin/bash
# Build-mode test for the bazel_cmake project (cmake_forge).
# Verifies that cmake_forge selects CMAKE_BUILD_TYPE=Release / Debug for the
# release / debug configs, and that the resulting binary runs correctly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIG="${1:-linux_x86_64}"
BUILD_MODES=("debug" "release")
declare -A TYPE_MAP=( ["debug"]="Debug" ["release"]="Release" )

forge_section "Testing Build Modes for Platform: $PLATFORM_CONFIG"

for mode in "${BUILD_MODES[@]}"; do
    forge_section "Testing build mode: $mode (platform: $PLATFORM_CONFIG)"
    forge_load_config "$PLATFORM_CONFIG"

    forge_build "$SRC_DIR" //:hello -- --config="$PLATFORM_CONFIG" --config="$mode" \
        || forge_die "build failed for $mode"

    BINARY=$(forge_cquery_files "$SRC_DIR" //:hello 'hello_cmake$' -- --config="$PLATFORM_CONFIG" --config="$mode")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"
    CMAKE_LOG=$(forge_find_cmake_log "$SRC_DIR" "$mode")

    forge_print_binary_info "$BINARY"

    forge_section "Verification: mode=$mode"
    forge_check_cpp_std_cmake "$SRC_DIR/CMakeLists.txt"
    if [ -n "$CMAKE_LOG" ]; then
        forge_check_cmake_build_type "$CMAKE_LOG" "${TYPE_MAP[$mode]}"
        forge_check_compiler "$CMAKE_LOG"
    else
        forge_die "CMake.log not found"
    fi
    forge_check_arch "$BINARY"
    forge_run_binary "$BINARY" "CMake integration test passed!"

    forge_pass "mode: $mode"
done

echo ""
echo "========================================="
echo "All build mode tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
