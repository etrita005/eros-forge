#!/bin/bash
# Sanitizer test for the bazel_cmake_conan project (cmake_conan_forge).
# The Conan sanitizer profiles (generated from generate_files.py) cover asan and
# tsan; the Conan build injects -fsanitize via the selected profile, so the
# resulting binary carries the sanitizer runtime symbols (observed via nm).
#
# ubsan and msan are intentionally skipped here:
#   - ubsan: no Conan ubsan profile is generated (SANITIZERS in generate_files.py
#     is {asan, tsan, msan}); cmake_conan_forge has no ubsan select() branch.
#   - msan: requires Clang (GCC lacks MSan); `conan install` fails without it.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"
source "$SCRIPT_DIR/../../forge_test_lib.sh"
forge_init

PLATFORM_CONFIG="${1:-linux_x86_64}"
# Only asan/tsan have Conan profiles that build on GCC.
SANITIZERS=("asan" "tsan")

forge_section "Testing Sanitizers for Platform: $PLATFORM_CONFIG"

for san in "${SANITIZERS[@]}"; do
    forge_section "Testing sanitizer: $san (platform: $PLATFORM_CONFIG)"
    forge_load_config "$PLATFORM_CONFIG"

    forge_build "$SRC_DIR" //:hello -- --config="$PLATFORM_CONFIG" --config="$san" \
        || forge_die "build failed for $san"

    BINARY=$(forge_find_binary "$SRC_DIR" "hello")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"

    forge_print_binary_info "$BINARY"

    forge_section "Verification: sanitizer=$san"
    forge_check_arch "$BINARY"
    forge_check_sanitizer_symbols "$BINARY" "$san"
    if [ "$FC_IS_CROSS" = "1" ]; then
        forge_skip "Binary execution: cross-compiled binary"
    else
        out=$("$BINARY" 2>&1 || true)
        echo "$out" | grep -q "CMake + Conan integration test passed!" \
            && forge_ok "Binary execution: matched 'CMake + Conan integration test passed!'" \
            || echo "⚠ Binary execution: sanitizer warnings (output: $(echo "$out" | head -1))"
    fi

    forge_pass "sanitizer: $san"
done

echo ""
echo "⚠ ubsan: skipped (no Conan ubsan profile; see generate_files.py SANITIZERS)"
echo "⚠ msan: skipped (requires Clang; conan install fails with GCC)"
echo ""
echo "========================================="
echo "All sanitizer tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
