#!/bin/bash
# Platform configuration test for the bazel_cmake_conan project (cmake_conan_forge).
# cmake_conan_forge builds via a custom action (not rules_foreign_cc), so there is
# no CMake.log; verification is artifact-based (architecture, dynamic linker,
# RUNPATH, exported symbols, execution). All platform expectations come from the
# shared config table.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIGS=(
    "linux_x86_64"
    "linux_arm64"
    "linux_x86_64_cross_arm64"
    "linux_arm64_cross_arm64"
)
if [ $# -gt 0 ]; then PLATFORM_CONFIGS=("$@"); fi

for config in "${PLATFORM_CONFIGS[@]}"; do
    forge_section "Testing platform config: $config"
    forge_load_config "$config"

    forge_section "Building with config: $config"
    forge_build "$SRC_DIR" //:hello -- --config="$config" || forge_die "build failed for $config"

    BINARY=$(forge_find_binary "$SRC_DIR" "hello")
    STATIC_LIB=$(forge_find_lib "$SRC_DIR" "libmylib_static.a")
    SHARED_LIB=$(forge_find_lib "$SRC_DIR" "libmylib_shared.so")
    [ -n "$BINARY" ]    && [ -f "$BINARY" ]    || forge_die "binary not found"
    [ -n "$STATIC_LIB" ] && [ -f "$STATIC_LIB" ] || forge_die "static lib not found"
    [ -n "$SHARED_LIB" ] && [ -f "$SHARED_LIB" ] || forge_die "shared lib not found"

    forge_print_binary_info "$BINARY"

    forge_section "Verification: $config"
    forge_check_linker "$BINARY"
    forge_check_rpath "$BINARY"
    forge_check_arch "$BINARY"
    forge_check_arch_objdump "$STATIC_LIB"
    forge_check_arch "$SHARED_LIB"
    forge_check_lib_symbols "$STATIC_LIB" "" 'T.*(calculate_sum|get_greeting|fibonacci)' 3
    forge_check_lib_symbols "$SHARED_LIB" "-D" 'T.*(calculate_sum|get_greeting|fibonacci)' 3
    forge_run_binary "$BINARY" "CMake + Conan integration test passed!"

    forge_pass "config: $config"
done

echo ""
echo "========================================="
echo "All platform config tests PASSED!"
echo "========================================="
