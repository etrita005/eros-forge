"""rules_foreign_cc CMake adapter with the same strict export/debug boundary."""

load("@rules_foreign_cc//foreign_cc:defs.bzl", "cmake")
load("@rules_foreign_cc//foreign_cc/private:cc_toolchain_util.bzl", "get_flags_info")
load("//bazel/config:variants.bzl", "cmake_toolchain")
load(":cmake_conan_forge.bzl", "cmake_build", "legacy_exports")

def _toolchain_file_impl(ctx):
    flags = get_flags_info(ctx)
    output = ctx.actions.declare_file(ctx.label.name + ".cmake")
    levels = "/".join([".."] * len(output.dirname.split("/")))
    lines = ['get_filename_component(_forge_exec_root "${CMAKE_CURRENT_LIST_DIR}/' + levels + '" ABSOLUTE)']
    for variable, values in {
        "CMAKE_C_FLAGS": flags.cc,
        "CMAKE_CXX_FLAGS": flags.cxx,
        "CMAKE_ASM_FLAGS": flags.assemble,
        "CMAKE_EXE_LINKER_FLAGS": flags.cxx_linker_executable,
        "CMAKE_SHARED_LINKER_FLAGS": flags.cxx_linker_shared,
        "CMAKE_MODULE_LINKER_FLAGS": flags.cxx_linker_shared,
    }.items():
        value = " ".join(["'" + flag.replace("'", "'\"'\"'") + "'" for flag in values])
        value += " " + ctx.attr.raw_flags.get(variable, "")
        value = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
        if ctx.attr.prefix_map and variable in ["CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS", "CMAKE_ASM_FLAGS"]:
            value += " '-ffile-prefix-map=${_forge_exec_root}=.'"
        lines.append('set(' + variable + ' "${' + variable + '_INIT} ' + value + '" CACHE STRING "Forge flags" FORCE)')
    # foreign_cc 0.15.1 flattens quoted arguments through environment strings.
    # The declared overlay preserves typed argv without changing upstream rules.
    ctx.actions.expand_template(template = ctx.file.file, output = output,
                                substitutions = {"# EROS_FORGE_FLAGS": "\n".join(lines)})
    return [DefaultInfo(files = depset([output]))]

_toolchain_file = rule(
    implementation = _toolchain_file_impl,
    attrs = {
        "file": attr.label(allow_single_file = True),
        "copts": attr.string_list(),
        "linkopts": attr.string_list(),
        "raw_flags": attr.string_dict(),
        "prefix_map": attr.bool(default = True),
        "deps": attr.label_list(),
        "_cc_toolchain": attr.label(default = Label("@bazel_tools//tools/cpp:current_cc_toolchain")),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
)

def _jobs_impl(ctx):
    return [platform_common.TemplateVariableInfo({"FORGE_JOBS": str(ctx.var.get("forge_jobs", ctx.attr.jobs))})]

_jobs = rule(implementation = _jobs_impl, attrs = {"jobs": attr.int(default = 2)})

def cmake_forge(name, cache_entries = {}, generate_crosstool_file = True, data = [],
                exports = None, jobs = 2, **kwargs):
    """Preserve lib_source/basic foreign_cc kwargs and validate installed outputs.

    Native toolchain features supply sanitizer/debug/link flags to foreign_cc.
    An explicit toolchain file still binds the generated Forge SDK selection.
    """
    toolchain = "_" + name + "_toolchain"
    copts = kwargs.pop("copts", []) + ["-g", "-fPIC"]
    prefix_map = kwargs.pop("set_file_prefix_map", True)
    _toolchain_file(name = toolchain, file = cmake_toolchain(), copts = copts,
                    linkopts = kwargs.get("linkopts", []), deps = kwargs.get("deps", []),
                    raw_flags = {key: value for key, value in cache_entries.items() if key.startswith("CMAKE_") and key.endswith("_FLAGS")},
                    prefix_map = prefix_map, features = kwargs.get("features", []),
                    testonly = kwargs.get("testonly", False))
    out_static = kwargs.get("out_static_libs", [])
    out_shared = kwargs.get("out_shared_libs", [])
    binaries = kwargs.get("out_binaries", [])
    descriptor = legacy_exports(name, "", out_static, out_shared, None, None, kwargs.get("linkopts", []), exports)
    descriptor["binaries"] = list(descriptor.get("binaries", [])) + ["bin/" + binary for binary in binaries]
    if not descriptor["libraries"] and not binaries and not kwargs.get("out_headers_only", False):
        lib_name = kwargs.get("lib_name", name)
        descriptor["libraries"] = [{"name": lib_name, "static": "lib/" + lib_name + ".a", "pic_static": "lib/" + lib_name + ".a"}]
    entries = dict(cache_entries)
    entries.update({
        "CMAKE_TOOLCHAIN_FILE": "$(execpath :" + toolchain + ")",
        "CMAKE_POSITION_INDEPENDENT_CODE": "ON",
        "CMAKE_BUILD_RPATH_USE_ORIGIN": "ON",
        "CMAKE_INSTALL_RPATH": "\\$$ORIGIN/../lib;\\$$ORIGIN",
    })
    release = dict(entries, CMAKE_BUILD_TYPE = "Release")
    debug = dict(entries, CMAKE_BUILD_TYPE = "Debug")
    build_data = kwargs.pop("build_data", [])
    tags = kwargs.pop("tags", [])
    visibility = kwargs.pop("visibility", ["//visibility:public"])
    testonly = kwargs.pop("testonly", False)
    jobs_target = "_" + name + "_jobs"
    _jobs(name = jobs_target, jobs = jobs, testonly = testonly)
    foreign = "_" + name + "_foreign"
    cmake(
        name = foreign,
        cache_entries = select({Label("//bazel/config:debug"): debug, "//conditions:default": release}),
        generate_crosstool_file = generate_crosstool_file,
        set_file_prefix_map = prefix_map,
        # build_data is exec-configured upstream. This overlay describes the
        # target's ABI/features, so it must remain in the target configuration.
        data = data + [":" + toolchain],
        build_data = build_data + [Label("@eros_host_tools//:env_manifest"), Label("@eros_host_tools//:all_tools"), Label("//bazel/toolchain:validate_environment")],
        build_args = kwargs.pop("build_args", ["--parallel", "$(FORGE_JOBS)"]),
        toolchains = kwargs.pop("toolchains", []) + [":" + jobs_target],
        copts = copts,
        tags = tags + ["no-remote-exec"],
        visibility = ["//visibility:private"],
        testonly = testonly,
        **kwargs
    )
    native.filegroup(name = "_" + name + "_install", srcs = [":" + foreign], output_group = "gen_dir", testonly = testonly)
    cmake_build(name = name, foreign_install = ":_" + name + "_install", exports_json = json.encode(descriptor),
                srcs = [kwargs["lib_source"]],
                deps = kwargs.get("deps", []), data = data, jobs = jobs, tags = tags,
                features = kwargs.get("features", []), target_compatible_with = kwargs.get("target_compatible_with", []),
                visibility = visibility, testonly = testonly)
