"""Module extension exposing host compiler toolchains as declared inputs.

For remote cache correctness, every cc action must declare the compiler and
binutils it uses as inputs. This extension locates the host's native GCC tools
and the aarch64-linux-gnu cross tools at fetch time, COPIES them (not symlinks)
into the @eros_host_tools repo, and exposes aggregated filegroups.

Copying (rather than symlinking) ensures the tool binary *content* is part of
each cc action's input digest, so two machines with different compiler versions
produce different action keys (no stale cross-machine cache hits). The repo is
fetched locally on each machine, so the copies always reflect that machine's
tools.
"""

_NATIVE_TOOLS = [
    "gcc", "g++", "ld", "ar", "as", "cpp", "gcov", "nm", "objdump", "strip",
    "objcopy", "dwp", "ranlib",
]
_CROSS_PREFIX = "aarch64-linux-gnu-"
_NAME_MAP = {"g++": "gxx"}

def _fname(basename):
    return _NAME_MAP.get(basename, basename)

def _find_conan(ctx):
    """Locate the conan executable, searching PATH, common install locations,
    and finally a login shell (which sources ~/.profile and picks up
    ~/.local/bin). Returns a path object or None."""
    p = ctx.which("conan")
    if p:
        return p
    home = ctx.os.environ.get("HOME", "")
    candidates = []
    if home:
        candidates.append(home + "/.local/bin/conan")
    candidates += ["/usr/local/bin/conan", "/usr/bin/conan"]
    for c in candidates:
        path = ctx.path(c)
        if path.exists:
            return path
    res = ctx.execute(["bash", "-lc", "command -v conan 2>/dev/null || true"])
    out = res.stdout.strip()
    if out:
        return ctx.path(out)
    return None

def _eros_host_tools_impl(ctx):
    copied_native = []
    copied_cross = []

    for basename in _NATIVE_TOOLS:
        p = ctx.which(basename)
        if p:
            dst = "native/" + _fname(basename)
            ctx.execute(["mkdir", "-p", "native"])
            ctx.execute(["cp", str(p), dst])
            copied_native.append(dst)

    for basename in _NATIVE_TOOLS:
        p = ctx.which(_CROSS_PREFIX + basename)
        if p:
            dst = "cross/" + _fname(basename)
            ctx.execute(["mkdir", "-p", "cross"])
            ctx.execute(["cp", str(p), dst])
            copied_cross.append(dst)

    # Locate the Conan 2 executable (a Python entry script). Copying it makes
    # the conan command a declared action input (its content is part of the
    # action digest). Note: the conan Python package itself still lives in the
    # host's site-packages, so this is not fully hermetic (long-term: managed
    # Conan). If conan is not found, no label is produced and consumers must
    # supply their own.
    conan_p = _find_conan(ctx)
    if conan_p:
        ctx.execute(["mkdir", "-p", "conan"])
        ctx.execute(["cp", str(conan_p), "conan/conan"])
        ctx.execute(["chmod", "+x", "conan/conan"])

    build = """package(default_visibility = ["//visibility:public"])

filegroup(
    name = "native_all",
    srcs = glob(["native/*"]),
)

filegroup(
    name = "cross_arm64_all",
    srcs = glob(["cross/*"]),
)

filegroup(
    name = "conan_tool",
    srcs = glob(["conan/*"]),
)
"""
    ctx.file("BUILD.bazel", build)

eros_host_tools_repo = repository_rule(
    implementation = _eros_host_tools_impl,
    attrs = {},
)

def _eros_host_tools_module_impl(module_ctx):
    eros_host_tools_repo(name = "eros_host_tools")

eros_host_tools = module_extension(implementation = _eros_host_tools_module_impl)
