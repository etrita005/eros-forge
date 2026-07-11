# Copyright (c) 2024 EROS Project
#
# Shared platform constraint lists. Loaded by BUILD.bazel to avoid duplicating
# the same constraint_values across every config_setting, platform, and
# eros_cc_toolchain. Editing a list here updates all dependent definitions
# in unison, preventing drift that could cause silent wrong-branch select()
# fallthrough or ambiguous-select errors.

NATIVE_X86_64 = [
    "@platforms//os:linux",
    "@platforms//cpu:x86_64",
    ":glibc_native",
]

NATIVE_ARM64 = [
    "@platforms//os:linux",
    "@platforms//cpu:arm64",
    ":glibc_native",
]

CROSS_ARM64 = [
    "@platforms//os:linux",
    "@platforms//cpu:arm64",
    ":glibc_cross",
]

EXEC_X86_64 = [
    "@platforms//os:linux",
    "@platforms//cpu:x86_64",
]

EXEC_ARM64 = [
    "@platforms//os:linux",
    "@platforms//cpu:arm64",
]
