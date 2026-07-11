#!/bin/bash
# Build-mode test for the bazel_simple project.
# Verifies debug (-O0, no NDEBUG, not stripped) and release (-O3, NDEBUG,
# symbols kept via separate_debug_info) for a given platform config.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIG="${1:-linux_x86_64}"
BUILD_MODES=("debug" "release")

declare -A OPT_MAP=( ["debug"]="-O0" ["release"]="-O3" )

forge_section "Testing Build Modes for Platform: $PLATFORM_CONFIG"

for mode in "${BUILD_MODES[@]}"; do
    forge_section "Testing build mode: $mode (platform: $PLATFORM_CONFIG)"
    forge_load_config "$PLATFORM_CONFIG"

    forge_build "$SRC_DIR" //:hello //:math_utils_static //:math_utils_shared -- \
        --config="$PLATFORM_CONFIG" --config="$mode" || forge_die "build failed for $mode"
    forge_aquery "$SRC_DIR" 'mnemonic("CppCompile", deps(//:hello))' -- \
        --config="$PLATFORM_CONFIG" --config="$mode"

    BINARY=$(forge_cquery_files "$SRC_DIR" //:hello 'hello$' -- --config="$PLATFORM_CONFIG" --config="$mode")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"

    forge_print_build_info "$FC_AQUERY_LOG"
    forge_print_binary_info "$BINARY"

    forge_section "Verification: mode=$mode"
    forge_check_cpp_std "$FC_AQUERY_LOG"
    forge_check_opt "$FC_AQUERY_LOG" "${OPT_MAP[$mode]}" 1
    if [ "$mode" = "release" ]; then
        forge_check_define "$FC_AQUERY_LOG" "NDEBUG"
        forge_check_symbol_status "$BINARY" "not stripped"
    else
        forge_check_no_define "$FC_AQUERY_LOG" "NDEBUG"
        forge_report_symbol_status "$BINARY"
    fi
    forge_run_binary "$BINARY" "All tests passed!"

    forge_pass "mode: $mode"
done

echo ""
echo "========================================="
echo "All build mode tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
