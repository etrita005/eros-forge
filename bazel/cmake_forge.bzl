load("@rules_foreign_cc//foreign_cc:cmake.bzl", "cmake")

def cmake_forge(name, **kwargs):
    cache_entries = kwargs.pop("cache_entries", {})
    generate_crosstool_file = kwargs.pop("generate_crosstool_file", False)
    data = kwargs.pop("data", [])
    
    # 根据 Bazel 的 compilation_mode 自动设置 CMAKE_BUILD_TYPE
    # 如果用户已经在 cache_entries 中设置了 CMAKE_BUILD_TYPE，则使用用户的设置
    cmake_build_type = select({
        "@eros_forge//bazel/toolchain:cmake_release": "Release",
        "@eros_forge//bazel/toolchain:cmake_debug": "Debug",
        "//conditions:default": "Release",  # 默认使用 Release
    })
    
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
    
    # 合并 cache_entries，用户的设置会覆盖自动设置的 CMAKE_BUILD_TYPE
    final_cache_entries = {
        "CMAKE_BUILD_TYPE": cmake_build_type,
        "CMAKE_TOOLCHAIN_FILE": "$(location :_{}_toolchain_file)".format(name),
    }
    final_cache_entries.update(cache_entries)
    
    cmake(
        name = name,
        cache_entries = final_cache_entries,
        generate_crosstool_file = generate_crosstool_file,
        data = data + [":_{}_toolchain_file".format(name)],
        **kwargs
    )
