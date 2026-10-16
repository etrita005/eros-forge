"""Instantiate complete toolchains and explicit unsupported-host rejection fallbacks."""

load("@rules_cc//cc:defs.bzl", "cc_toolchain")
load(":cc_toolchain_config.bzl", "cc_toolchain_config")
load(":constraints.bzl", "exec_constraints", "target_constraints")
load(":toolchain_data.bzl", "EROS_TOOLCHAINS")

_REGISTRATIONS = {
    "linux_x86_64": "cc-toolchain-linux-x86_64",
    "linux_arm64": "cc-toolchain-linux-arm64",
    "linux_x86_64_cross_arm64": "cc-toolchain-x86_64-to-arm64",
    "linux_arm64_cross_arm64": "cc-toolchain-arm64-to-arm64",
}

def declare_eros_toolchains():
    for preset, cfg in EROS_TOOLCHAINS.items():
        native.platform(name = preset + "_platform", constraint_values = target_constraints(cfg))
        cc_toolchain_config(name = preset + "_config", preset = preset)
        inputs = ":cross_arm64_inputs" if cfg["is_cross"] else ":native_inputs"
        cc_toolchain(
            name = preset + "_cc_toolchain",
            toolchain_identifier = "eros-gcc13-" + preset,
            toolchain_config = ":" + preset + "_config",
            all_files = inputs,
            compiler_files = inputs,
            linker_files = inputs,
            dwp_files = inputs,
            objcopy_files = inputs,
            strip_files = inputs,
            supports_param_files = 1,
        )
        native.toolchain(
            name = _REGISTRATIONS[preset],
            exec_compatible_with = exec_constraints(cfg["host_cpu"]),
            target_compatible_with = target_constraints(cfg),
            toolchain = ":" + preset + "_cc_toolchain",
            toolchain_type = "@rules_cc//cc:toolchain_type",
        )
        # Before rules_cc's auto-detected native fallback, fail rather than silently
        # compiling a cross preset with a different toolchain on an unsupported host.
        native.toolchain(
            name = "reject-unsupported-" + preset.replace("_", "-").replace("x86-64", "x86_64"),
            target_compatible_with = target_constraints(cfg),
            toolchain = ":" + preset + "_cc_toolchain",
            toolchain_type = "@rules_cc//cc:toolchain_type",
        )
