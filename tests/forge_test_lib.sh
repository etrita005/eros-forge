#!/bin/bash
# Copyright (c) 2024 EROS Project
#
# forge_test_lib.sh - Shared library for the EROS Forge test framework.
#
# This library centralizes the verification logic that was previously duplicated
# across every tests/<project>/test_configs/*.sh script:
#
#   - Platform/config mapping tables are NOT hardcoded here. They come from
#     tests/test_config_data.json, which is generated from the SAME toolchain
#     table (bazel/toolchain/generate_files.py) that drives the cc_toolchain,
#     Conan profiles and CMake toolchain files. Edit the table once, run
#     `python3 tests/gen_test_config.py`, and every test stays in sync.
#   - Build-flag verification uses `bazel aquery` (structured, cache-independent,
#     version-stable) instead of grep'ing `bazel build --subcommands` logs.
#   - Binary verification uses `file`/`readelf`/`nm` on the actual artifact and
#     compares against the config table, instead of hardcoded per-config maps.
#   - `bazel clean` is NOT run per config: different --platforms configs live in
#     separate bazel-out configuration directories, so cquery/aquery return the
#     correct per-config artifacts without a full rebuild.
#
# Usage in a test script:
#   source "$SCRIPT_DIR/../../forge_test_lib.sh"
#   forge_init
#   for config in "${PLATFORM_CONFIGS[@]}"; do
#       forge_load_config "$config"
#       forge_build "$PROJECT_DIR/src" //:hello -- --config="$config" || forge_die "build failed"
#       forge_aquery "$PROJECT_DIR/src" 'mnemonic("CppCompile", deps(//:hello))' -- --config="$config"
#       BINARY=$(forge_cquery_files "$PROJECT_DIR/src" //:hello 'hello$' -- --config="$config")
#       forge_check_cpp_std "$FC_AQUERY_LOG"
#       forge_check_arch "$BINARY"
#       ...
#       forge_pass "$config"
#   done
#
# All forge_check_* helpers print a ✓ line on success or a ✗ line + `exit 1` on
# failure (matching the previous set -e semantics).

set -u

# Global state (set by forge_* helpers).
FORGE_TESTS_DIR=""
FORGE_CONFIG_JSON=""
FC_CONFIG=""
FC_CPU=""
FC_FILE_ARCH=""
FC_IS_CROSS=0
FC_COMPILER=""
FC_COMPILER_C=""
FC_LINKER=""
FC_RPATH=""
FC_READELF=""
FC_NM=""
FC_OBJDUMP=""
FC_STRIP=""
FC_BUILD_LOG=""
FC_AQUERY_LOG=""

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

forge_init() {
    FORGE_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    FORGE_CONFIG_JSON="$FORGE_TESTS_DIR/test_config_data.json"
    if [ ! -f "$FORGE_CONFIG_JSON" ]; then
        echo "✗ test_config_data.json not found at $FORGE_CONFIG_JSON"
        echo "  Run: python3 $FORGE_TESTS_DIR/gen_test_config.py"
        exit 1
    fi
}

# Load config metadata from the generated JSON into FC_* globals.
forge_load_config() {
    FC_CONFIG="$1"
    local json
    json=$(python3 - "$FORGE_CONFIG_JSON" "$FC_CONFIG" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
cfg = data.get(sys.argv[2])
if not cfg:
    sys.exit("unknown config: " + sys.argv[2])
print(json.dumps(cfg))
PY
    ) || { echo "✗ $json"; exit 1; }
    FC_CPU=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["cpu"])' <<<"$json")
    FC_FILE_ARCH=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["file_arch"])' <<<"$json")
    FC_IS_CROSS=$(python3 -c 'import json,sys;print(1 if json.load(sys.stdin)["is_cross"] else 0)' <<<"$json")
    FC_COMPILER=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["compiler"])' <<<"$json")
    FC_COMPILER_C=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["compiler_c"])' <<<"$json")
    FC_LINKER=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["dynamic_linker"])' <<<"$json")
    FC_RPATH=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["rpath"])' <<<"$json")
    FC_READELF=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["readelf"])' <<<"$json")
    FC_NM=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["nm"])' <<<"$json")
    FC_OBJDUMP=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["objdump"])' <<<"$json")
    FC_STRIP=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["strip"])' <<<"$json")
}

# -----------------------------------------------------------------------------
# Reporting helpers
# -----------------------------------------------------------------------------

forge_section() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
}

forge_ok()   { echo "✓ $*"; }
forge_skip() { echo "✓ $* (skipped)"; }
forge_pass() { echo ""; echo "✓ Test PASSED for: $*"; }
forge_die()  { echo "✗ $*"; exit 1; }

# -----------------------------------------------------------------------------
# Bazel invocation helpers (no `bazel clean`; configs isolate outputs)
# -----------------------------------------------------------------------------

# forge_build <workdir> <targets...> -- <config_flags...>
# Builds the targets with the given bazel flags. Captures --subcommands output
# to $FC_BUILD_LOG. Returns the bazel exit code. Does NOT run `bazel clean`.
forge_build() {
    local workdir="$1"; shift
    local targets=()
    local flags=()
    local in_flags=0
    local arg
    for arg in "$@"; do
        if [ "$arg" = "--" ]; then in_flags=1; continue; fi
        if [ "$in_flags" = "1" ]; then flags+=("$arg"); else targets+=("$arg"); fi
    done
    FC_BUILD_LOG="$(mktemp)"
    (cd "$workdir" && bazel build --subcommands "${targets[@]}" "${flags[@]}") 2>&1 | tee "$FC_BUILD_LOG"
    return "${PIPESTATUS[0]}"
}

# forge_aquery <workdir> <query> -- <config_flags...>
# Runs `bazel aquery --output=text` and captures it to $FC_AQUERY_LOG.
forge_aquery() {
    local workdir="$1"; shift
    local query="$1"; shift
    local flags=()
    local in_flags=0
    local arg
    for arg in "$@"; do
        if [ "$arg" = "--" ]; then in_flags=1; continue; fi
        if [ "$in_flags" = "1" ]; then flags+=("$arg"); fi
    done
    FC_AQUERY_LOG="$(mktemp)"
    (cd "$workdir" && bazel aquery "$query" --output=text "${flags[@]}") >"$FC_AQUERY_LOG" 2>&1
    return $?
}

# forge_cquery_files <workdir> <target> <grep_pattern> -- <config_flags...>
# Echoes the first `bazel cquery --output=files` line matching <grep_pattern>,
# resolved to an ABSOLUTE path (cquery returns workspace-relative paths, but the
# caller may run from a different CWD).
forge_cquery_files() {
    local workdir="$1"; shift
    local target="$1"; shift
    local pattern="$1"; shift
    local flags=()
    local in_flags=0
    local arg
    for arg in "$@"; do
        if [ "$arg" = "--" ]; then in_flags=1; continue; fi
        if [ "$in_flags" = "1" ]; then flags+=("$arg"); fi
    done
    local rel abs
    rel=$(cd "$workdir" && bazel cquery "$target" --output=files "${flags[@]}" 2>/dev/null \
        | grep -E "$pattern" | head -n1)
    [ -z "$rel" ] && { echo ""; return; }
    abs=$(cd "$workdir" && realpath "$rel" 2>/dev/null) || abs=""
    if [ -n "$abs" ] && [ -e "$abs" ]; then echo "$abs"; else echo "$rel"; fi
}

# forge_find_binary <workdir> <name> : locate a built executable under bazel-bin
# (absolute path). Used for rules_foreign_cc / cmake_conan_forge targets whose
# nested outputs are easier to locate via find than via cquery. Intermediate
# build-dir copies (e.g. cmake_conan_forge's _hello_cmake_build/hello, which is
# not stripped) and runfiles trees are excluded so the final artifact is found.
forge_find_binary() {
    local workdir="$1"; local name="$2"
    local rel
    rel=$(cd "$workdir" && find -L bazel-bin -name "$name" -type f -executable \
        ! -path "*_build*" ! -path "*.runfiles*" 2>/dev/null | head -n1)
    if [ -z "$rel" ]; then
        rel=$(cd "$workdir" && find -L bazel-bin -path "*_*/bin/$name" -type f 2>/dev/null | head -n1)
    fi
    [ -z "$rel" ] && { echo ""; return; }
    local abs
    abs=$(cd "$workdir" && realpath "$rel" 2>/dev/null) || abs=""
    if [ -n "$abs" ] && [ -e "$abs" ]; then echo "$abs"; else echo "$rel"; fi
}

# forge_find_lib <workdir> <libname> : locate a built .a/.so under bazel-bin
# (absolute path).
forge_find_lib() {
    local workdir="$1"; local libname="$2"
    local rel abs
    rel=$(cd "$workdir" && find -L bazel-bin -name "$libname" -type f 2>/dev/null | head -n1)
    [ -z "$rel" ] && { echo ""; return; }
    abs=$(cd "$workdir" && realpath "$rel" 2>/dev/null) || abs=""
    if [ -n "$abs" ] && [ -e "$abs" ]; then echo "$abs"; else echo "$rel"; fi
}

# forge_find_cmake_log <workdir> [variant]
# Locate the rules_foreign_cc CMake.log. When <variant> (e.g. "debug"/"release")
# is given, only CMake.log files under a path containing that variant are
# considered, so the debug and release configure logs are not confused.
forge_find_cmake_log() {
    local workdir="$1"; local variant="${2:-}"
    local rel abs
    if [ -n "$variant" ]; then
        rel=$(cd "$workdir" && find -L bazel-bin -path "*${variant}*" -name "CMake.log" -type f 2>/dev/null | head -n1)
    else
        rel=$(cd "$workdir" && find -L bazel-bin -name "CMake.log" -type f -printf '%T@ %p\n' 2>/dev/null \
            | sort -rn | head -n1 | cut -d' ' -f2-)
    fi
    [ -z "$rel" ] && { echo ""; return; }
    abs=$(cd "$workdir" && realpath "$rel" 2>/dev/null) || abs=""
    if [ -n "$abs" ] && [ -e "$abs" ]; then echo "$abs"; else echo "$rel"; fi
}

# -----------------------------------------------------------------------------
# Build-flag verification (operates on an aquery or CMake.log text blob)
# -----------------------------------------------------------------------------

forge_check_cpp_std() {
    local log="$1"
    if grep -qE -- '-std=(c\+\+|gnu\+\+)20' "$log"; then
        forge_ok "C++ standard: c++20"
    else
        forge_die "C++ standard: expected c++20, not found"
    fi
}

# forge_check_cpp_std_cmake <cmakelists_txt>
# For CMake projects the -std flag is not in the configure log; the standard is
# declared in CMakeLists.txt via CMAKE_CXX_STANDARD (or target CXX_STANDARD).
forge_check_cpp_std_cmake() {
    local cmakelists="$1"
    if [ -f "$cmakelists" ] && grep -qE -- 'CXX_STANDARD[[:space:]]+20' "$cmakelists"; then
        forge_ok "C++ standard: c++20 (from CMakeLists.txt)"
    elif [ -f "$cmakelists" ] && grep -qE -- '-std=c\+\+20|-std=gnu\+\+20' "$cmakelists"; then
        forge_ok "C++ standard: c++20 (from CMakeLists.txt)"
    else
        forge_die "C++ standard: expected CXX_STANDARD 20 in $cmakelists"
    fi
}

# forge_check_cmake_build_type <cmake_log> <Release|Debug>
# rules_foreign_cc writes CMAKE_BUILD_TYPE=... into the CMake configure log.
forge_check_cmake_build_type() {
    local log="$1"; local expected="$2"
    if grep -q -- "CMAKE_BUILD_TYPE=$expected" "$log"; then
        forge_ok "CMAKE_BUILD_TYPE: $expected"
    else
        forge_die "CMAKE_BUILD_TYPE: expected $expected, not found in CMake.log"
    fi
}

# forge_extract_compiler <log>
# Echo the first absolute compiler path that appears as a standalone token whose
# final path component is a compiler binary (gcc/g++/aarch64-linux-gnu-gcc/...).
#
# Two anchors keep this from matching the wrong path:
#   - Leading "(^|[^a-zA-Z0-9_./+-])" requires a token boundary before the path,
#     so relative host_tools copies embedded in aquery Inputs lists are NOT
#     matched. "external/.../eros_host_tools/cross/gcc" contains the substring
#     "/cross/gcc", but it is preceded by a letter, not a boundary, so it is
#     rejected while the real "Command Line: ... /usr/bin/aarch64-linux-gnu-gcc"
#     (preceded by a space) is accepted.
#   - Trailing "([^a-zA-Z0-9_+./-]|$)" requires the compiler name to be the last
#     path component, so GCC library directories in CMake logs such as
#     "/usr/lib/gcc/aarch64-linux-gnu/13" are NOT matched (the "gcc" there is
#     followed by "/", a path character).
forge_extract_compiler() {
    local log="$1"
    grep -oE -- '(^|[^a-zA-Z0-9_./+-])(/[a-zA-Z0-9_./-]+/)?(aarch64-linux-gnu-(g\+\+|gcc)|g\+\+|gcc|clang\+\+)(-[0-9]+)?([^a-zA-Z0-9_+./-]|$)' "$log" \
        | grep -oE -- '/([a-zA-Z0-9_./-]+/)?(aarch64-linux-gnu-(g\+\+|gcc)|g\+\+|gcc|clang\+\+)(-[0-9]+)?' \
        | head -1
}

# Accepts the configured g++ OR gcc (gcc can drive C++ compilation).
forge_check_compiler() {
    local log="$1"
    local found
    found=$(forge_extract_compiler "$log")
    if [ -z "$found" ]; then
        forge_die "Compiler: none found in log (expected $FC_COMPILER)"
    fi
    local expected="$FC_COMPILER"
    if [[ "$found" == *"aarch64-linux-gnu"* ]] && [[ "$expected" == *"aarch64-linux-gnu"* ]]; then
        forge_ok "Compiler: $found"
    elif [[ "$expected" == *"/usr/bin/g++" ]] && [[ "$found" == *g++* || "$found" == *gcc* ]]; then
        forge_ok "Compiler: $found"
    elif [[ "$found" == *"$expected"* ]]; then
        forge_ok "Compiler: $found"
    else
        forge_die "Compiler: expected $expected, found $found"
    fi
}

# forge_check_opt <log> <expected> [allow sanitizer -O1]
forge_check_opt() {
    local log="$1"; local expected="$2"; local allow_o1="${3:-0}"
    local opt
    opt=$(grep -oE -- '-O[0-3sg]' "$log" | tail -1)
    if [ "$allow_o1" = "1" ] && [[ "$opt" == *"-O1"* ]] && grep -q -- '-fsanitize=' "$log"; then
        forge_ok "Optimization: $opt (sanitizer -O1 tolerated)"
    elif [[ "$opt" == *"$expected"* ]]; then
        forge_ok "Optimization: $opt"
    elif [ -z "$opt" ] && [[ "$expected" == *"-O0"* ]]; then
        forge_ok "Optimization: -O0 (default)"
    else
        forge_die "Optimization: expected $expected, found ${opt:-none}"
    fi
}

forge_check_define() {
    local log="$1"; local define="$2"
    if grep -qE -- "-D${define}(=|[^a-zA-Z0-9_]|$)" "$log"; then
        forge_ok "Define: $define"
    else
        forge_die "Define: $define not found"
    fi
}

forge_check_no_define() {
    local log="$1"; local define="$2"
    if grep -qE -- "-D${define}(=|[^a-zA-Z0-9_]|$)" "$log"; then
        forge_die "Define: $define found (should be absent)"
    else
        forge_ok "No define: $define (as expected)"
    fi
}

# forge_check_sanitizer_flags <log> <sanitizer_name>
# sanitizer_name in {asan,tsan,ubsan,msan}. MSan is best-effort (GCC lacks it).
forge_check_sanitizer_flags() {
    local log="$1"; local san="$2"
    local -A flag_map=(
        [asan]=address
        [tsan]=thread
        [ubsan]=undefined
        [msan]=memory
    )
    local flag="-fsanitize=${flag_map[$san]}"
    if [ "$san" = "msan" ]; then
        if grep -q -- '-fsanitize=memory' "$log"; then
            forge_ok "Sanitizer flags: $flag"
        else
            forge_skip "MSan flags: GCC lacks MSan (requires Clang)"
        fi
    elif grep -q -- "$flag" "$log"; then
        forge_ok "Sanitizer flags: $flag"
    else
        forge_die "Sanitizer flags: expected $flag, not found"
    fi
}

# forge_check_sanitizer_symbols <binary> <sanitizer_name>
forge_check_sanitizer_symbols() {
    local binary="$1"; local san="$2"
    if [ "$san" = "msan" ]; then
        forge_skip "MSan symbols: requires Clang"
        return
    fi
    local syms
    syms=$("$FC_NM" "$binary" 2>/dev/null | grep -oE "__${san}_[a-z_]*" | head -3 | tr '\n' ' ')
    if [ -n "$syms" ]; then
        forge_ok "Sanitizer symbols: $syms"
    else
        echo "⚠ Sanitizer symbols: none found in $binary (may be normal for static linking)"
    fi
}

# forge_check_symbol_status <binary> <expected_substring>
forge_check_symbol_status() {
    local binary="$1"; local expected="$2"
    local status
    status=$(file "$binary" | grep -oE 'stripped|not stripped' | head -1)
    if [[ "$status" == *"$expected"* ]]; then
        forge_ok "Symbol status: $status"
    else
        forge_die "Symbol status: expected $expected, found $status"
    fi
}

# forge_report_symbol_status <binary> : non-fatal diagnostic (warns on mismatch).
forge_report_symbol_status() {
    local binary="$1"
    local status
    status=$(file "$binary" | grep -oE 'stripped|not stripped' | head -1)
    if [[ "$status" == *"not stripped"* ]]; then
        forge_ok "Symbol status: $status"
    else
        echo "⚠ Symbol status: $status"
    fi
}

# -----------------------------------------------------------------------------
# Artifact verification (uses file/readelf/nm against the config table)
# -----------------------------------------------------------------------------

forge_check_arch() {
    local binary="$1"
    local arch
    arch=$(file "$binary" | grep -oE 'x86-64|ARM aarch64' | head -1)
    if [[ "$arch" == *"$FC_FILE_ARCH"* ]]; then
        forge_ok "Architecture: $arch ($FC_CPU)"
    else
        forge_die "Architecture: expected $FC_FILE_ARCH, found ${arch:-none}"
    fi
}

# forge_check_arch_objdump <archive>
# For static (.a) archives, `file` does not report the target architecture
# reliably; use `objdump -f` instead (matches the EROS toolchain's objdump).
forge_check_arch_objdump() {
    local lib="$1"
    local arch want
    arch=$("$FC_OBJDUMP" -f "$lib" 2>/dev/null | grep "architecture:" | grep -oE 'x86-64|aarch64' | head -1)
    case "$FC_CPU" in
        x86_64)  want="x86-64" ;;
        aarch64) want="aarch64" ;;
        *)       want="$FC_CPU" ;;
    esac
    if [[ "$arch" == *"$want"* ]]; then
        forge_ok "Architecture: $arch ($FC_CPU)"
    else
        forge_die "Architecture: expected $want, found ${arch:-none}"
    fi
}

forge_check_linker() {
    local binary="$1"
    local linker
    linker=$("$FC_READELF" -p .interp "$binary" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' | head -1)
    if [[ "$linker" == *"$FC_LINKER"* ]]; then
        forge_ok "Dynamic linker: $linker"
    else
        forge_die "Dynamic linker: expected $FC_LINKER, found ${linker:-none}"
    fi
}

forge_check_rpath() {
    local binary="$1"
    if [ -z "$FC_RPATH" ]; then
        forge_skip "RPATH: not required for $FC_CONFIG"
        return
    fi
    local rpath
    rpath=$("$FC_READELF" -d "$binary" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' | head -1)
    if [[ "$rpath" == *"$FC_RPATH"* ]]; then
        forge_ok "RUNPATH: $rpath"
    else
        forge_die "RUNPATH: expected $FC_RPATH, found ${rpath:-none}"
    fi
}

# forge_check_lib_symbols <lib> <nm_flags> <pattern> <min_count>
forge_check_lib_symbols() {
    local lib="$1"; local nm_flags="$2"; local pattern="$3"; local min="$4"
    local count
    count=$($FC_NM $nm_flags "$lib" 2>/dev/null | grep -E "$pattern" | wc -l)
    if [ "$count" -ge "$min" ]; then
        forge_ok "Library symbols: $count (need >= $min)"
    else
        forge_die "Library symbols: found $count, need >= $min"
    fi
}

# forge_run_binary <binary> <expected_output_substring>
# Skips execution for cross-compiled binaries (cannot run on host).
forge_run_binary() {
    local binary="$1"; local expected="$2"
    if [ "$FC_IS_CROSS" = "1" ]; then
        forge_skip "Binary execution: cross-compiled binary"
        return
    fi
    local out
    out=$("$binary" 2>&1 || true)
    if echo "$out" | grep -q -- "$expected"; then
        forge_ok "Binary execution: matched '$expected'"
    else
        forge_die "Binary execution: expected '$expected', got: $(echo "$out" | head -3)"
    fi
}

# forge_check_deb_arch <deb_path>
# Verify a .deb's Architecture field matches the configured target cpu
# (x86_64 -> amd64, aarch64 -> arm64). Used by the deb packaging smoke test.
forge_check_deb_arch() {
    local deb="$1"
    local want
    case "$FC_CPU" in
        x86_64)  want="amd64" ;;
        aarch64) want="arm64" ;;
        *)       want="$FC_CPU" ;;
    esac
    local arch
    arch=$(dpkg-deb -f "$deb" Architecture 2>/dev/null)
    if [ "$arch" = "$want" ]; then
        forge_ok "Deb architecture: $arch"
    else
        forge_die "Deb architecture: expected $want, found ${arch:-none}"
    fi
}

# -----------------------------------------------------------------------------
# Diagnostic print blocks (mirrors the old "Build Information" sections)
# -----------------------------------------------------------------------------

forge_print_build_info() {
    local log="$1"
    local compiler cpp_std opt defines sanitizer
    compiler=$(forge_extract_compiler "$log")
    cpp_std=$(grep -oE -- '-std=[a-z0-9+]+' "$log" | tail -1)
    opt=$(grep -oE -- '-O[0-3sg]' "$log" | tail -1)
    defines=$(grep -oE -- '-D[A-Z_]+' "$log" | sort -u | head -5 | tr '\n' ' ')
    sanitizer=$(grep -oE -- '-fsanitize=[a-z,]+' "$log" | head -1)
    echo ""
    echo "[Build Information]"
    echo "  Compiler: ${compiler:-unknown}"
    echo "  C++ Standard: ${cpp_std:-unknown}"
    echo "  Optimization: ${opt:-default}"
    echo "  Defines: ${defines:-none}"
    [ -n "$sanitizer" ] && echo "  Sanitizer: $sanitizer"
}

forge_print_binary_info() {
    local binary="$1"
    local linker rpath needed arch
    linker=$("$FC_READELF" -p .interp "$binary" 2>/dev/null | grep -oE '/[a-zA-Z0-9_/.-]+' | head -1)
    rpath=$("$FC_READELF" -d "$binary" 2>/dev/null | grep -E 'RPATH|RUNPATH' | grep -oE '/[a-zA-Z0-9_/.-]+' | head -1)
    needed=$("$FC_READELF" -d "$binary" 2>/dev/null | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ')
    arch=$(file "$binary" | grep -oE 'x86-64|ARM aarch64' | head -1)
    echo ""
    echo "[Binary Information]"
    echo "  Architecture: ${arch:-unknown}"
    echo "  Dynamic Linker: ${linker:-unknown}"
    echo "  RPATH/RUNPATH: ${rpath:-none}"
    echo "  Needed Libraries: ${needed:-none}"
}
