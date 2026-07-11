#!/bin/bash
# Cross-module dependency consumption test for the bazel_cmake_conan project.
# Builds the consumer project (which links the CMake+Conan-exported static +
# shared libs and headers) and verifies the resulting binaries' architecture,
# dynamic linker, RUNPATH and execution.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONSUMER_DIR="$PROJECT_DIR/consumer"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIGS=(
    "linux_x86_64"
    "linux_arm64"
    "linux_x86_64_cross_arm64"
    "linux_arm64_cross_arm64"
)
if [ $# -gt 0 ]; then PLATFORM_CONFIGS=("$@"); fi

forge_section "Dependency Consumption Test: bazel_cmake_conan"

for config in "${PLATFORM_CONFIGS[@]}"; do
    forge_section "Testing platform config: $config"
    forge_load_config "$config"

    forge_build "$CONSUMER_DIR" //:consumer_static -- --config="$config" || forge_die "consumer_static build failed"
    STATIC=$(forge_cquery_files "$CONSUMER_DIR" //:consumer_static 'consumer_static$' -- --config="$config")
    [ -n "$STATIC" ] && [ -f "$STATIC" ] || forge_die "consumer_static binary not found"
    forge_print_binary_info "$STATIC"
    forge_check_arch "$STATIC"
    forge_check_linker "$STATIC"
    forge_check_rpath "$STATIC"
    forge_run_binary "$STATIC" "Consumer dependency test passed!"

    forge_build "$CONSUMER_DIR" //:consumer_shared -- --config="$config" || forge_die "consumer_shared build failed"
    SHARED=$(forge_cquery_files "$CONSUMER_DIR" //:consumer_shared 'consumer_shared$' -- --config="$config")
    [ -n "$SHARED" ] && [ -f "$SHARED" ] || forge_die "consumer_shared binary not found"
    forge_print_binary_info "$SHARED"
    forge_check_arch "$SHARED"
    forge_run_binary "$SHARED" "Consumer dependency test passed!"

    forge_pass "dependency consumption: $config"
done

echo ""
echo "========================================="
echo "All dependency consumption tests PASSED!"
echo "========================================="
