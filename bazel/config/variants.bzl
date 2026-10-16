"""One select vocabulary for CMake toolchains and Conan build/host profiles."""

load("//bazel/toolchain:constraints.bzl", "target_constraints")
load("//bazel/toolchain:toolchain_data.bzl", "EROS_TOOLCHAINS", "SANITIZERS")

def _label(name):
    return Label("//bazel/config:" + name)

def declare_variant_settings():
    """Declare disjoint explicit-preset and native-auto select conditions."""
    for sanitizer in ["none"] + SANITIZERS:
        native.config_setting(name = "sanitizer_" + sanitizer, flag_values = {":sanitizer": sanitizer})
    native.config_setting(name = "debug", values = {"compilation_mode": "dbg"})
    native.config_setting(name = "release", values = {"compilation_mode": "opt"})
    for preset, cfg in EROS_TOOLCHAINS.items():
        for automatic in ([False] if cfg["is_cross"] else [False, True]):
            prefix = ("auto_" if automatic else "") + preset
            flags = {":preset": "auto" if automatic else preset}
            native.config_setting(name = prefix, constraint_values = target_constraints(cfg), flag_values = flags)
            for mode in ["debug", "release"]:
                values = {"compilation_mode": "dbg"} if mode == "debug" else {}
                native.config_setting(name = prefix + "_" + mode, constraint_values = target_constraints(cfg), flag_values = dict(flags, **{":sanitizer": "none"}), values = values)
            for sanitizer in SANITIZERS:
                native.config_setting(name = prefix + "_" + sanitizer, constraint_values = target_constraints(cfg), flag_values = dict(flags, **{":sanitizer": sanitizer}), values = {"compilation_mode": "dbg"})

def cmake_toolchain():
    choices = {}
    for preset, cfg in EROS_TOOLCHAINS.items():
        value = Label("//bazel/toolchain/cmake:" + preset + ".cmake")
        choices[_label(preset)] = value
        if not cfg["is_cross"]:
            choices[_label("auto_" + preset)] = value
    return select(choices, no_match_error = "Unsupported Forge target/preset combination; select a supported --config=linux_* preset.")

def conan_host_profile():
    choices = {}
    for preset, cfg in EROS_TOOLCHAINS.items():
        for suffix in ["release", "debug"] + SANITIZERS:
            value = Label("//bazel/toolchain/conan:" + preset + "_" + suffix + ".profile")
            choices[_label(preset + "_" + suffix)] = value
            if not cfg["is_cross"]:
                choices[_label("auto_" + preset + "_" + suffix)] = value
    return select(choices, no_match_error = "Unsupported Forge Conan host variant. Sanitizers require Debug mode and a canonical sanitizer config.")

def conan_build_profile():
    choices = {}
    for preset, cfg in EROS_TOOLCHAINS.items():
        for suffix in ["release", "debug"] + SANITIZERS:
            mode = "release" if suffix == "release" else "debug"
            value = Label("//bazel/toolchain/conan:" + preset + "_build_" + mode + ".profile")
            choices[_label(preset + "_" + suffix)] = value
            if not cfg["is_cross"]:
                choices[_label("auto_" + preset + "_" + suffix)] = value
    return select(choices, no_match_error = "Unsupported Forge Conan build-machine variant.")

def cmake_build_type():
    return select({_label("debug"): "Debug", "//conditions:default": "Release"})
