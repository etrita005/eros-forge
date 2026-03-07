load("@rules_foreign_cc//foreign_cc:cmake.bzl", "cmake")

def cmake_forge(name, **kwargs):
    cache_entries = kwargs.pop("cache_entries", {})
    generate_crosstool_file = kwargs.pop("generate_crosstool_file", False)
    data = kwargs.pop("data", [])
    
    native.filegroup(
        name = "_{}_toolchain_file".format(name),
        srcs = select({
            "@eros_forge//bazel/toolchain:linux_x86_64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64_cross_arm64.cmake"],
            "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64_cross_arm64.cmake"],
            "//conditions:default": [],
        }),
        visibility = ["//visibility:private"],
    )
    
    cmake(
        name = name,
        cache_entries = cache_entries | {
            "CMAKE_TOOLCHAIN_FILE": "$(location :_{}_toolc
            hain_file)".format(name),
        },
        generate_crosstool_file = generate_crosstool_file,
        data = data + [":_{}_toolchain_file".format(name)],
        **kwargs
    )
