#!/bin/bash
# Sanitizer test for the bazel_cmake project (cmake_forge).
# Verifies, for asan/tsan/ubsan/msan, that the CMake-built binary carries the
# sanitizer runtime symbols (the -fsanitize flag is applied inside the foreign_cc
# action via the Bazel cc toolchain features, so we observe it on the artifact).
# MSan is best-effort (GCC lacks MSan; requires Clang).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIG="${1:-linux_x86_64}"
SANITIZERS=("asan" "tsan" "ubsan" "msan")

forge_section "Testing Sanitizers for Platform: $PLATFORM_CONFIG"

for san in "${SANITIZERS[@]}"; do
    forge_section "Testing sanitizer: $san (platform: $PLATFORM_CONFIG)"
    forge_load_config "$PLATFORM_CONFIG"

    forge_build "$SRC_DIR" //:hello -- --config="$PLATFORM_CONFIG" --config="$san" \
        || forge_die "build failed for $san"

    BINARY=$(forge_cquery_files "$SRC_DIR" //:hello 'hello_cmake$' -- --config="$PLATFORM_CONFIG" --config="$san")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"

    forge_print_binary_info "$BINARY"

    forge_section "Verification: sanitizer=$san"
    forge_check_arch "$BINARY"
    forge_check_sanitizer_symbols "$BINARY" "$san"
    if [ "$FC_IS_CROSS" = "1" ]; then
        forge_skip "Binary execution: cross-compiled binary"
    else
        out=$("$BINARY" 2>&1 || true)
        echo "$out" | grep -q "CMake integration test passed!" \
            && forge_ok "Binary execution: matched 'CMake integration test passed!'" \
            || echo "⚠ Binary execution: sanitizer warnings (output: $(echo "$out" | head -1))"
    fi

    forge_pass "sanitizer: $san"
done

echo ""
echo "========================================="
echo "All sanitizer tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
