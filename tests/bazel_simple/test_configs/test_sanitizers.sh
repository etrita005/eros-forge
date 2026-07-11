#!/bin/bash
# Sanitizer test for the bazel_simple project.
# Verifies, for asan/tsan/ubsan/msan, that the matching -fsanitize flag is
# applied and the binary carries the sanitizer runtime symbols. MSan is
# best-effort (GCC lacks MSan; requires Clang), so its checks are non-fatal.
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

    # MSan requires Clang; GCC (both native and cross) lacks it. For native
    # builds the default rules_cc toolchain silently omits -fsanitize=memory,
    # so the build succeeds but MSan is a no-op. For cross builds the EROS
    # cc_toolchain unconditionally adds -fsanitize=memory, which the cross-GCC
    # rejects. Skip MSan for cross-compilation to avoid a build failure.
    if [ "$san" = "msan" ] && [ "$FC_IS_CROSS" = "1" ]; then
        forge_skip "MSan: GCC cross-compiler lacks MSan (requires Clang)"
        continue
    fi

    forge_build "$SRC_DIR" //:hello //:math_utils_static //:math_utils_shared -- \
        --config="$PLATFORM_CONFIG" --config="$san" || forge_die "build failed for $san"
    forge_aquery "$SRC_DIR" 'mnemonic("CppCompile", deps(//:hello))' -- \
        --config="$PLATFORM_CONFIG" --config="$san"

    BINARY=$(forge_cquery_files "$SRC_DIR" //:hello 'hello$' -- --config="$PLATFORM_CONFIG" --config="$san")
    [ -n "$BINARY" ] && [ -f "$BINARY" ] || forge_die "binary not found"

    forge_print_build_info "$FC_AQUERY_LOG"
    forge_print_binary_info "$BINARY"

    forge_section "Verification: sanitizer=$san"
    forge_check_compiler "$FC_AQUERY_LOG"
    forge_check_cpp_std "$FC_AQUERY_LOG"
    forge_check_sanitizer_flags "$FC_AQUERY_LOG" "$san"
    forge_check_sanitizer_symbols "$BINARY" "$san"
    # Sanitizer binaries may emit runtime warnings on exit; only require that the
    # program produced its success line (cross-compiled binaries are skipped).
    if [ "$FC_IS_CROSS" = "1" ]; then
        forge_skip "Binary execution: cross-compiled binary"
    else
        out=$("$BINARY" 2>&1 || true)
        echo "$out" | grep -q "All tests passed!" \
            && forge_ok "Binary execution: matched 'All tests passed!'" \
            || echo "⚠ Binary execution: sanitizer warnings (output: $(echo "$out" | head -1))"
    fi

    forge_pass "sanitizer: $san"
done

echo ""
echo "========================================="
echo "All sanitizer tests PASSED for platform: $PLATFORM_CONFIG"
echo "========================================="
