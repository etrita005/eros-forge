"""Analysis-time contract shared by native and foreign build paths."""

load("@eros_host_tools//:tools.bzl", "HOST_CPU")
load("//bazel/toolchain:toolchain_data.bzl", "EROS_TOOLCHAINS", "SANITIZER_FEATURES")
load(":settings.bzl", "ForgeBuildSettingInfo")

VARIANT_ATTRS = {
    "_sanitizer": attr.label(default = Label("//bazel/config:sanitizer")),
    "_preset": attr.label(default = Label("//bazel/config:preset")),
}

def normalize_sanitizer(flag, features, disabled_features = []):
    """Normalize legal feature combinations without losing a repeated config."""
    requested = [name for name in ["asan", "ubsan", "tsan", "msan"] if name in features and name not in disabled_features]
    if "msan" in requested:
        fail("MSan is not supported by Forge's GCC toolchains.")
    if "tsan" in requested and len(requested) != 1:
        fail("TSan cannot be combined with ASan or UBSan; only ASan+UBSan is supported.")
    effective = "asan_ubsan" if requested == ["asan", "ubsan"] else (requested[0] if requested else "none")
    if effective == "asan_ubsan" and flag in ["asan", "ubsan", "asan_ubsan"]:
        return effective
    if requested != SANITIZER_FEATURES[flag]:
        fail("Forge sanitizer flag %r does not match enabled features %s. Use a canonical --config=asan, ubsan, tsan, asan_ubsan, or no_sanitizer so all build paths match." % (flag, requested))
    return effective

def validate_configuration(ctx):
    """Reject flags that would give native, CMake and Conan different semantics."""
    sanitizer = normalize_sanitizer(ctx.attr._sanitizer[ForgeBuildSettingInfo].value, ctx.features, ctx.disabled_features)
    preset = ctx.attr._preset[ForgeBuildSettingInfo].value
    if preset != "auto" and EROS_TOOLCHAINS[preset]["host_cpu"] != HOST_CPU:
        fail("Forge preset %s requires a %s Linux execution host; this host is %s. Installed cross drivers do not change the supported host matrix." % (preset, EROS_TOOLCHAINS[preset]["host_cpu"], HOST_CPU))
    mode = ctx.var.get("COMPILATION_MODE", "fastbuild")
    if sanitizer != "none" and mode != "dbg":
        fail("Forge sanitizer %s requires Debug mode; do not combine sanitizer configs with --config=release." % sanitizer)
    build_type = "Debug" if mode == "dbg" else "Release"
    if ctx.var.get("cmake_build_type", build_type) != build_type:
        fail("cmake_build_type disagrees with Bazel compilation_mode; use --config=debug or --config=release consistently.")
    if "eros_sysroot" in ctx.var:
        fail("eros_sysroot cannot be overridden: the target SDK/glibc is fixed by the Forge preset.")
    flags = ctx.fragments.cpp.copts + ctx.fragments.cpp.cxxopts + ctx.fragments.cpp.conlyopts + ctx.fragments.cpp.linkopts
    for flag in flags:
        if "sanitize" in flag:
            fail("Do not pass sanitizer flags via copts/linkopts (%s); use --config=asan, ubsan, tsan or asan_ubsan so Conan and CMake match." % flag)
        if "--sysroot" in flag or "--dynamic-linker" in flag or "-dynamic-linker" in flag:
            fail("Target SDK/glibc overrides are unsupported: %s" % flag)
        if sanitizer != "none" and flag in ["-static", "-static-pie"]:
            fail("Static executable linking is incompatible with Forge sanitizer configurations: %s" % flag)
    return struct(preset = preset, sanitizer = sanitizer, build_type = build_type)
