#!/bin/bash
# Platform configuration test for the bazel_simple project.
# Verifies, for each platform config, that the cc_binary / static lib / shared
# lib are built for the correct architecture with the correct compiler, C++
# standard, dynamic linker and RUNPATH. All expected values come from the shared
# config table (tests/test_config_data.json), not from hardcoded per-config maps.
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
    forge_build "$SRC_DIR" //:hello //:math_utils_static //:math_utils_shared -- --config="$config" \
        || forge_die "build failed for $config"
    forge_aquery "$SRC_DIR" 'mnemonic("CppCompile", deps(//:hello))' -- --config="$config"

    BINARY=$(forge_cquery_files "$SRC_DIR" //:hello 'hello$' -- --config="$config")
    STATIC_LIB=$(forge_cquery_files "$SRC_DIR" //:math_utils_static '\.a$' -- --config="$config")
    SHARED_LIB=$(forge_cquery_files "$SRC_DIR" //:math_utils_shared '\.so$' -- --config="$config")
    [ -n "$BINARY" ]   && [ -f "$BINARY" ]   || forge_die "binary not found"
    [ -n "$STATIC_LIB" ] && [ -f "$STATIC_LIB" ] || forge_die "static lib not found"
    [ -n "$SHARED_LIB" ] && [ -f "$SHARED_LIB" ] || forge_die "shared lib not found"

    forge_print_build_info "$FC_AQUERY_LOG"
    forge_print_binary_info "$BINARY"

    forge_section "Verification: $config"
    forge_check_compiler "$FC_AQUERY_LOG"
    forge_check_cpp_std "$FC_AQUERY_LOG"
    forge_check_linker "$BINARY"
    forge_check_rpath "$BINARY"
    forge_check_arch "$BINARY"
    forge_check_arch_objdump "$STATIC_LIB"
    forge_check_arch "$SHARED_LIB"
    forge_check_lib_symbols "$STATIC_LIB" "" 'T.*(calculate_sum|get_greeting|fibonacci)' 3
    forge_check_lib_symbols "$SHARED_LIB" "-D" 'T.*(calculate_sum|get_greeting|fibonacci)' 3
    forge_run_binary "$BINARY" "All tests passed!"

    forge_pass "config: $config"
done

echo ""
echo "========================================="
echo "All platform config tests PASSED!"
echo "========================================="
