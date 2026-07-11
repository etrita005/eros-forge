#!/bin/bash
# Deb packaging smoke test for the bazel_simple project.
# Builds the //:hello_deb target (which uses pkg_eros_deb with auto-selected
# architecture) and verifies the resulting .deb has the correct Architecture
# field for the configured platform, and that the version honors
# --define=DEB_VERSION. Uses a genrule data tar so it works under any platform
# config (including cross-compilation) without requiring /opt/eros.
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
    forge_section "Testing deb packaging: $config"
    forge_load_config "$config"

    # Build with an explicit version via --define (cache-correct versioning).
    forge_build "$SRC_DIR" //:hello_deb -- --config="$config" --define=DEB_VERSION=1.2.3 \
        || forge_die "deb build failed for $config"

    DEB=$(forge_find_lib "$SRC_DIR" "hello_deb.deb")
    [ -z "$DEB" ] && DEB=$(cd "$SRC_DIR" && find -L bazel-bin -name "hello_deb*.deb" -type f 2>/dev/null \
        | grep -v '_amd64\|_arm64' | head -n1)
    [ -z "$DEB" ] && DEB=$(cd "$SRC_DIR" && find -L bazel-bin -name "*.deb" -type f 2>/dev/null | head -n1)
    [ -n "$DEB" ] && [ -f "$DEB" ] || forge_die "deb file not found"

    forge_section "Verification: deb $config"
    forge_check_deb_arch "$DEB"
    version=$(dpkg-deb -f "$DEB" Version 2>/dev/null)
    if [ "$version" = "1.2.3" ]; then
        forge_ok "Deb version: $version (from --define=DEB_VERSION)"
    else
        forge_die "Deb version: expected 1.2.3, found ${version:-none}"
    fi
    pkg=$(dpkg-deb -f "$DEB" Package 2>/dev/null)
    [ "$pkg" = "eros-hello" ] && forge_ok "Deb package name: $pkg" || forge_die "Deb package name: expected eros-hello, found ${pkg:-none}"

    forge_pass "deb packaging: $config"
done

echo ""
echo "========================================="
echo "All deb packaging tests PASSED!"
echo "========================================="
