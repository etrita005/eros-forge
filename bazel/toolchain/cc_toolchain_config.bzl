"""GCC 13 C/C++/assembly/link/archive configuration for the four Forge presets."""

load("@eros_host_tools//:tools.bzl", "HOST_CPU", "TOOLCHAINS")
load("@rules_cc//cc:cc_toolchain_config_lib.bzl", "feature", "flag_group", "flag_set", "tool_path")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")
load("//bazel/config:validation.bzl", "VARIANT_ATTRS", "validate_configuration")
load(":toolchain_data.bzl", "EROS_TOOLCHAINS", "SANITIZER_FEATURES", "SANITIZER_FLAGS", "TOOL_NAMES")

_COMPILE = ["c-compile", "c++-compile", "c++-header-parsing", "c++-module-compile", "c++-module-codegen", "linkstamp-compile"]
_ASSEMBLE = ["assemble", "preprocess-assemble"]
_LINK = ["c++-link-executable", "c++-link-dynamic-library", "c++-link-nodeps-dynamic-library"]

def _flags(actions, flags):
    return flag_set(actions = actions, flag_groups = [flag_group(flags = flags)])

def _impl(ctx):
    cfg = EROS_TOOLCHAINS[ctx.attr.preset]
    if cfg["host_cpu"] != HOST_CPU:
        fail("Forge preset %s requires a %s Linux execution host; this host is %s. Installed cross drivers do not make this preset supported." % (ctx.attr.preset, cfg["host_cpu"], HOST_CPU))
    variant = validate_configuration(ctx)
    if variant.preset != "auto" and variant.preset != ctx.attr.preset:
        fail("Forge preset %s disagrees with the selected target platform/toolchain %s; do not override the preset's --platforms/SDK." % (variant.preset, ctx.attr.preset))
    if variant.preset == "auto" and cfg["is_cross"]:
        fail("Forge auto selects native only; choose the complete cross --config preset instead of overriding --platforms.")
    installed = TOOLCHAINS[cfg["tools_set"]]
    features = [
        feature(name = "supports_pic", enabled = True),
        feature(name = "supports_dynamic_linker", enabled = True),
        feature(name = "dbg", flag_sets = [_flags(_COMPILE, ["-O0", "-g", "-fno-omit-frame-pointer"])]),
        feature(name = "opt", flag_sets = [_flags(_COMPILE, ["-O3", "-DNDEBUG", "-g", "-fno-omit-frame-pointer"])]),
        feature(name = "fastbuild", flag_sets = [_flags(_COMPILE, ["-O3", "-DNDEBUG", "-g", "-fno-omit-frame-pointer"])]),
        feature(name = "cxx20", enabled = True, flag_sets = [_flags(["c++-compile", "c++-header-parsing", "c++-module-compile"], ["-std=gnu++20"])]),
        feature(name = "default_link_flags", enabled = True, flag_sets = [_flags(_LINK, ["-lstdc++", "-lm", "-Wl,--build-id=sha1"])]),
        feature(name = "dependency_file", enabled = True, flag_sets = [flag_set(
            actions = _COMPILE + ["preprocess-assemble"],
            flag_groups = [flag_group(flags = ["-MD", "-MF", "%{dependency_file}"], expand_if_available = "dependency_file")],
        )]),
        feature(name = "static_cpp_runtime", flag_sets = [_flags(_LINK, ["-static-libstdc++", "-static-libgcc"])]),
        # Native wrapper rules export .debug files; this deliberately is not split DWARF.
        feature(name = "separate_debug_info", flag_sets = [_flags(_COMPILE, ["-g"])]),
        feature(name = "coverage", flag_sets = [_flags(_COMPILE, ["--coverage"]), _flags(_LINK, ["--coverage"])]),
    ]
    selected = SANITIZER_FEATURES[variant.sanitizer]
    forbidden_symbols = []
    for name in ["asan", "ubsan", "tsan", "msan"]:
        symbol = "Forge_%s_requires_matching_sanitizer_flag_MSAN_is_unsupported" % name
        features.append(feature(name = name, provides = [symbol]))
        if name not in selected:
            forbidden_symbols.append(symbol)
    features.append(feature(name = "eros_variant_guard", enabled = True, provides = forbidden_symbols))
    if variant.sanitizer != "none":
        flags = SANITIZER_FLAGS[variant.sanitizer]
        features.append(feature(
            name = "eros_sanitizer_flags",
            enabled = True,
            flag_sets = [
                _flags(_COMPILE, flags + ["-g", "-O0", "-fno-omit-frame-pointer", "-fno-optimize-sibling-calls"]),
                _flags(_LINK, flags),
            ],
        ))
    if cfg["is_cross"]:
        features.append(feature(
            name = "eros_cross_driver",
            enabled = True,
            flag_sets = [_flags(_COMPILE + _ASSEMBLE + _LINK, ["-B/usr/bin/aarch64-linux-gnu-"])],
        ))
        features.append(feature(
            name = "eros_deployment_runtime",
            enabled = True,
            flag_sets = [
                _flags(_LINK, ["-Wl,-rpath," + cfg["sdk_path"] + "/lib"]),
                _flags(["c++-link-executable"], ["-Wl,--dynamic-linker=" + cfg["dynamic_interpreter"]]),
            ],
        ))
    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        features = features,
        cxx_builtin_include_directories = installed["builtin_includes"],
        tool_paths = [tool_path(name = name, path = installed["tools"][name]) for name in TOOL_NAMES if name != "ranlib" and name != "readelf"],
        toolchain_identifier = "eros-gcc13-" + ctx.attr.preset,
        host_system_name = cfg["host_triple"],
        target_system_name = cfg["target_triple"],
        target_cpu = "aarch64" if cfg["target_cpu"] == "arm64" else "x86_64",
        target_libc = "glibc_cross" if cfg["is_cross"] else "glibc_native",
        compiler = "gcc",
        abi_version = cfg["target_triple"],
        abi_libc_version = "eros-sdk" if cfg["is_cross"] else "native",
    )

cc_toolchain_config = rule(
    implementation = _impl,
    attrs = dict(VARIANT_ATTRS, preset = attr.string(mandatory = True)),
    fragments = ["cpp"],
    provides = [CcToolchainConfigInfo],
)
