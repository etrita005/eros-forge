#!/usr/bin/env bash
# Explicitly export the controlled ARM64 compiler runtime; never install it.
set -euo pipefail
export LC_ALL=C
unset GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH LD_LIBRARY_PATH LD_PRELOAD \
    CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH TAR_OPTIONS GZIP CDPATH GLOBIGNORE

usage() {
    printf '%s\n' \
        'Usage: bash bazel/toolchain/export_runtime.sh --output PATH.tar.gz [--compiler GCC]' \
        'Export GCC 13 AArch64 Linux runtime libraries to opt/eros/lib in a tar.gz.' \
        'Default compiler: aarch64-linux-gnu-gcc-13. Existing output is never replaced.'
}

fail() {
    printf 'Forge runtime export failed: %s\n' "$*" >&2
    exit 1
}

compiler=aarch64-linux-gnu-gcc-13
output=
while (( $# )); do
    case "$1" in
        --compiler|--output)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            case "$1" in
                --compiler) compiler=$2 ;;
                --output) output=$2 ;;
            esac
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ -n "$output" ]] || { usage >&2; exit 2; }
[[ "$output" == *.tar.gz || "$output" == *.tgz ]] || fail 'output must end in .tar.gz or .tgz'
[[ ! -e "$output" && ! -L "$output" ]] || fail "output already exists: $output"
(( BASH_VERSINFO[0] >= 4 )) || fail 'Bash 4 or newer is required'
for tool in realpath sha256sum timeout mktemp cp chmod sort tar gzip ln; do
    command -v "$tool" >/dev/null || fail "required tool not found: $tool"
done
compiler=$(command -v -- "$compiler") || fail 'compiler not found'
compiler=$(realpath -e -- "$compiler")
target=$(timeout 120 "$compiler" -dumpmachine)
[[ "$target" == aarch64-linux-gnu ]] || fail "expected aarch64-linux-gnu, found $target"
version=$(timeout 120 "$compiler" -dumpfullversion -dumpversion)
[[ "$version" == 13 || "$version" == 13.* ]] || fail "expected GCC 13, found $version"
readelf=$(command -v -- "$target-readelf") || fail "required tool not found: $target-readelf"
readelf=$(realpath -e -- "$readelf")
output_dir=$(cd -- "$(dirname -- "$output")" && pwd -P)
output="$output_dir/$(basename -- "$output")"

work=$(mktemp -d "${TMPDIR:-/tmp}/forge-runtime.XXXXXX")
archive=
trap 'rm -rf -- "$work"; [[ -z "$archive" ]] || rm -f -- "$archive"' EXIT
root="$work/root/opt/eros"
mkdir -p -- "$root/lib"
umask 022

safe_name() {
    [[ "$1" != . && "$1" != .. && "$1" =~ ^[-a-zA-Z0-9_.+]+$ ]] || fail "unsafe library name: $1"
}

file_hash() {
    local checksum
    checksum=$(sha256sum < "$1")
    printf '%s' "${checksum%% *}"
}

alias_to() {
    local name=$1 destination=$2
    safe_name "$name"
    [[ "$name" != "$destination" ]] || return 0
    if [[ -e "$root/lib/$name" || -L "$root/lib/$name" ]]; then
        [[ -L "$root/lib/$name" && "$(readlink -- "$root/lib/$name")" == "$destination" ]] || \
            fail "library name collision: $name"
    else
        ln -s -- "$destination" "$root/lib/$name"
    fi
}

pending=(libc.so.6 libm.so.6 libstdc++.so.6 libgcc_s.so.1 ld-linux-aarch64.so.1
         libdl.so.2 libpthread.so.0 librt.so.1 libatomic.so.1 libutil.so.1 libresolv.so.2
         libasan.so libubsan.so libtsan.so)
declare -A required=() visited=() payload_hashes=()
for name in "${pending[@]:0:5}"; do
    required[$name]=1
done
missing=()
soname_pattern='\(SONAME\).*\[([^]]+)\]'
needed_pattern='\(NEEDED\).*\[([^]]+)\]'
: > "$work/sources"
for (( index=0; index<${#pending[@]}; index++ )); do
    name=${pending[index]}
    safe_name "$name"
    [[ -z "${visited[$name]:-}" ]] || continue
    path=$(timeout 120 "$compiler" "-print-file-name=$name")
    if [[ "$path" == "$name" ]]; then
        [[ -z "${required[$name]:-}" ]] || fail "required runtime library not found: $name"
        missing+=("$name")
        continue
    fi
    [[ "$path" == /* && -f "$path" ]] || fail "invalid compiler runtime path for $name: $path"
    real=$(realpath -e -- "$path")
    base=$(basename -- "$real")
    safe_name "$base"
    elf=$(timeout 120 "$readelf" --file-header --dynamic -- "$real") || fail "invalid runtime ELF: $real"
    [[ "$elf" =~ Machine:[[:space:]]+AArch64 && "$elf" =~ Class:[[:space:]]+ELF64 && \
       "$elf" == *'little endian'* && "$elf" =~ Type:[[:space:]]+DYN ]] || \
        fail "runtime must be an AArch64 ELF64 little-endian shared object: $real"
    soname=
    dependencies=()
    while IFS= read -r line; do
        if [[ "$line" =~ $soname_pattern ]]; then
            soname=${BASH_REMATCH[1]}
        elif [[ "$line" =~ $needed_pattern ]]; then
            dependencies+=("${BASH_REMATCH[1]}")
        fi
    done <<< "$elf"
    [[ -n "$soname" ]] || fail "runtime ELF has no SONAME: $real"
    safe_name "$soname"
    [[ "$name" == "$soname" || "$name" == "${soname%%.so*}.so" ]] || \
        fail "runtime SONAME mismatch: requested $name, found $soname"
    checksum=$(file_hash "$real")
    if [[ -n "${payload_hashes[$base]:-}" ]]; then
        [[ "${payload_hashes[$base]}" == "$checksum" ]] || fail "library name collision: $base"
    else
        [[ ! -e "$root/lib/$base" && ! -L "$root/lib/$base" ]] || fail "library name collision: $base"
        cp -- "$real" "$root/lib/$base"
        [[ "$(file_hash "$root/lib/$base")" == "$checksum" ]] || fail "runtime changed while copying: $real"
        chmod 755 "$root/lib/$base"
        payload_hashes[$base]=$checksum
    fi
    alias_to "$soname" "$base"
    alias_to "$name" "$base"
    visited[$name]=1
    visited[$soname]=1
    printf '%q\t%s\t%s\tlib/%s\n' "$real" "$soname" "$checksum" "$base" >> "$work/sources"
    for dependency in "${dependencies[@]}"; do
        safe_name "$dependency"
        required[$dependency]=1
        pending+=("$dependency")
    done
done

{
    printf 'format_version=1\ntarget_triple=%s\ngcc_version=%s\n' "$target" "$version"
    printf 'compiler=%q\ncompiler_sha256=%s\n' "$compiler" "$(file_hash "$compiler")"
    printf 'readelf=%q\nreadelf_sha256=%s\n' "$readelf" "$(file_hash "$readelf")"
    printf 'install_root=/opt/eros/lib\n'
    printf '\n[source_shell_escaped\tsoname\tsha256\tarchive_file]\n'
    sort -u "$work/sources"
    printf '\n[relative_symlinks]\n'
    for path in "$root"/lib/*; do
        if [[ -L "$path" ]]; then
            printf 'lib/%s -> %s\n' "$(basename -- "$path")" "$(readlink -- "$path")"
        fi
    done
    printf '\n[unavailable_optional_queries]\n'
    if (( ${#missing[@]} )); then
        printf '%s\n' "${missing[@]}" | sort -u
    fi
} > "$root/TOOLCHAIN"
(
    cd -- "$root"
    sha256sum TOOLCHAIN lib/* > SHA256SUMS
)
chmod 644 "$root/TOOLCHAIN" "$root/SHA256SUMS"
chmod 755 "$work/root" "$work/root/opt" "$root" "$root/lib"
archive=$(mktemp "$output_dir/.forge-runtime.XXXXXX")
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner --format=ustar \
    --directory="$work/root" --create --file=- opt | gzip -n > "$archive"
chmod 644 "$archive"
# Publish atomically without following or replacing an existing destination.
ln --no-target-directory -- "$archive" "$output" || fail "cannot publish output (it may already exist): $output"
printf 'Exported AArch64 GCC %s runtime to %s\n' "$version" "$output"
