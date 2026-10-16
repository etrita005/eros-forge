"""Bind foreign_cc to the same declared installed tools as custom actions."""

load("@eros_host_tools//:tools.bzl", "HOST_CPU", "HOST_TOOLS")
load("@rules_foreign_cc//toolchains/native_tools:native_tools_toolchain.bzl", "native_tool_toolchain")

def declare_foreign_tools():
    for tool, environment in {"cmake": "CMAKE", "make": "MAKE", "pkgconfig": "PKG_CONFIG", "m4": "M4"}.items():
        if tool not in HOST_TOOLS:
            continue
        native_tool_toolchain(name = "foreign_" + tool, path = HOST_TOOLS[tool], env = {environment: HOST_TOOLS[tool]})
        native.toolchain(
            name = "foreign_" + tool + "_toolchain",
            toolchain = ":foreign_" + tool,
            toolchain_type = "@rules_foreign_cc//toolchains:" + tool + "_toolchain",
            exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:" + HOST_CPU],
        )
