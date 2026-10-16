"""Locked Conan snapshots and strict CMake install/export rules.

exports is an analysis-time dict: headers/includes/defines/linkopts lists,
libraries=[{name, static?, pic_static?, shared?, alwayslink?}], and optional
binaries/runtime_files lists. File paths are exact, install-relative paths.
"""

load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@rules_cc//cc:defs.bzl", "CcInfo", "cc_common")
load("//bazel/config:validation.bzl", "VARIANT_ATTRS", "validate_configuration")
load("//bazel/config:variants.bzl", "cmake_toolchain", "conan_build_profile", "conan_host_profile")
load("//bazel:providers.bzl", "ErosDebugInfo", "ErosInstallInfo")

ConanSnapshotInfo = provider(fields = {"snapshot": "Complete materialized dependency tree.", "manifest": "Locked package/file identities."})

def _enabled(ctx, feature):
    return feature in ctx.features and feature not in ctx.disabled_features

def _action_attrs():
    attrs = dict(VARIANT_ATTRS)
    attrs.update({
        "jobs": attr.int(default = 2),
        "_environment": attr.label(default = Label("@eros_host_tools//:env_manifest"), allow_single_file = True),
        "_tools": attr.label(default = Label("@eros_host_tools//:all_tools")),
        "_validated": attr.label(default = Label("//bazel/toolchain:validate_environment")),
        "_common": attr.label(default = Label("//bazel/tools:action_common.py"), allow_single_file = True),
    })
    return attrs

def _run(ctx, script, config, inputs, outputs, mnemonic):
    if ctx.attr.jobs < 1:
        fail("jobs must be positive")
    config_file = ctx.actions.declare_file(ctx.label.name + ".action.json")
    ctx.actions.write(config_file, json.encode(config))
    ctx.actions.run(
        executable = "/usr/bin/python3",
        arguments = ["-s", script.path, "--config", config_file.path],
        inputs = depset([script, config_file, ctx.file._common, ctx.file._environment] + inputs,
                        transitive = [ctx.attr._tools[DefaultInfo].files, ctx.attr._validated[DefaultInfo].files]),
        outputs = outputs,
        env = {"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        execution_requirements = {"no-remote-exec": "1"},
        mnemonic = mnemonic,
        progress_message = "%s %s (locked, isolated, strict outputs)" % (mnemonic, ctx.label),
    )

def _conan_install_impl(ctx):
    variant = validate_configuration(ctx)
    snapshot = ctx.actions.declare_directory(ctx.label.name + ".snapshot")
    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    debug = ctx.actions.declare_directory(ctx.label.name + ".debug")
    debug_manifest = ctx.actions.declare_file(ctx.label.name + ".debug_manifest.json")
    remote_root = ""
    if ctx.files.file_remote:
        for file in ctx.files.file_remote:
            if "/recipes/" not in file.path:
                fail("file_remote inputs must use the Conan local-recipes-index recipes/<name>/ layout: " + file.path)
            candidate = file.path.split("/recipes/")[0]
            if remote_root and candidate != remote_root:
                fail("file_remote must contain exactly one index root")
            remote_root = candidate
    inputs = [ctx.file.conanfile, ctx.file.lockfile, ctx.file.host_profile, ctx.file.build_profile,
              ctx.file._deployer] + ctx.files.extra_srcs + ctx.files.file_remote + ctx.files.local_recipes
    for file in [ctx.file.remote_config, ctx.file.cache_archive]:
        if file:
            inputs.append(file)
    _run(ctx, ctx.file._driver, {
        "output": snapshot.path,
        "manifest": manifest.path,
        "debug_output": debug.path,
        "debug_manifest": debug_manifest.path,
        "environment": ctx.file._environment.path,
        "preset": variant.preset,
        "conanfile": ctx.file.conanfile.path,
        "extra_srcs": [file.path for file in ctx.files.extra_srcs],
        "lockfile": ctx.file.lockfile.path,
        "host_profile": ctx.file.host_profile.path,
        "build_profile": ctx.file.build_profile.path,
        "deployer": ctx.file._deployer.path,
        "local_recipes": [file.path for file in ctx.files.local_recipes if file.basename == "conanfile.py"],
        "file_remote": remote_root,
        "remote_config": ctx.file.remote_config.path if ctx.file.remote_config else "",
        "cache_archive": ctx.file.cache_archive.path if ctx.file.cache_archive else "",
        "separate_debug": _enabled(ctx, "separate_debug_info"),
        "sanitizer": variant.sanitizer,
        "copts": ctx.fragments.cpp.copts,
        "conlyopts": ctx.fragments.cpp.conlyopts,
        "cxxopts": ctx.fragments.cpp.cxxopts,
        "linkopts": ctx.fragments.cpp.linkopts + (["-static-libgcc", "-static-libstdc++"] if _enabled(ctx, "static_cpp_runtime") else []),
        "jobs": int(ctx.var.get("forge_jobs", ctx.attr.jobs)),
    }, inputs, [snapshot, manifest, debug, debug_manifest], "ConanInstall")
    symbols = depset([debug, debug_manifest])
    return [
        DefaultInfo(files = depset([snapshot, manifest])),
        ConanSnapshotInfo(snapshot = snapshot, manifest = manifest),
        ErosDebugInfo(files = depset([debug]), manifests = depset([debug_manifest])),
        OutputGroupInfo(eros_debug_info = symbols),
    ]

_conan_attrs = _action_attrs()
_conan_attrs.update({
    "conanfile": attr.label(mandatory = True, allow_single_file = True),
    "lockfile": attr.label(mandatory = True, allow_single_file = True, doc = "Ordinary builds never create/update this lock."),
    "host_profile": attr.label(mandatory = True, allow_single_file = True),
    "build_profile": attr.label(mandatory = True, allow_single_file = True),
    "extra_srcs": attr.label_list(allow_files = True),
    "file_remote": attr.label_list(allow_files = True),
    "local_recipes": attr.label_list(allow_files = True),
    "remote_config": attr.label(allow_single_file = True, doc = "HTTP remote URLs plus pinned ref/package_id/prev/file hashes."),
    "cache_archive": attr.label(allow_single_file = True, doc = "Optional declared conan cache save archive, never a user home."),
    "_driver": attr.label(default = Label("//bazel/tools:conan_action.py"), allow_single_file = True),
    "_deployer": attr.label(default = Label("//bazel/tools:snapshot_deployer.py"), allow_single_file = True),
})

conan_install = rule(implementation = _conan_install_impl, attrs = _conan_attrs, fragments = ["cpp"])

def _relative(path):
    if not path or path.startswith("/") or ".." in path.split("/") or "\\" in path:
        fail("export paths must be nonempty install-relative paths: %r" % path)
    return path

def _cmake_build_impl(ctx):
    variant = validate_configuration(ctx)
    descriptor = json.decode(ctx.attr.exports_json)
    install = ctx.actions.declare_directory(ctx.label.name + ".install")
    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    debug = ctx.actions.declare_directory(ctx.label.name + ".debug")
    debug_manifest = ctx.actions.declare_file(ctx.label.name + ".debug_manifest.json")
    declared = {}
    kinds = {}
    names = {}
    for path in descriptor.get("headers", []) + descriptor.get("binaries", []) + descriptor.get("runtime_files", []):
        declared[_relative(path)] = None
    for library in descriptor.get("libraries", []):
        if not library.get("name") or not any([library.get(kind) for kind in ["static", "pic_static", "shared"]]):
            fail("each export library needs a logical name and at least one static/pic_static/shared path")
        if library["name"] in names:
            fail("put static/shared alternatives in one descriptor for logical library " + library["name"])
        names[library["name"]] = True
        for kind in ["static", "pic_static", "shared"]:
            if library.get(kind):
                declared[_relative(library[kind])] = None
                kinds[library[kind]] = "shared" if kind == "shared" else "archive"
    for path in descriptor.get("binaries", []):
        kinds[path] = "executable"
    for path in declared.keys():
        declared[path] = ctx.actions.declare_file(ctx.label.name + ".exports/" + path)
    sources = ctx.files.srcs + ctx.files.extra_srcs
    inputs = list(sources) + ctx.files.data
    conan = ctx.attr.conan_deps[ConanSnapshotInfo] if ctx.attr.conan_deps else None
    foreign = ctx.file.foreign_install
    if ctx.file.cmake_lists:
        sources.append(ctx.file.cmake_lists)
        inputs.append(ctx.file.cmake_lists)
    if ctx.file.toolchain:
        inputs.append(ctx.file.toolchain)
    if conan:
        inputs += [conan.snapshot, conan.manifest]
    if foreign:
        inputs.append(foreign)
    _run(ctx, ctx.file._driver, {
        "output": install.path,
        "manifest": manifest.path,
        "debug_output": debug.path,
        "debug_manifest": debug_manifest.path,
        "environment": ctx.file._environment.path,
        "preset": variant.preset,
        "source_root": ctx.file.cmake_lists.dirname if ctx.file.cmake_lists else "",
        "sources": [file.path for file in depset(sources).to_list()],
        "toolchain": ctx.file.toolchain.path if ctx.file.toolchain else "",
        "conan_snapshot": conan.snapshot.path if conan else "",
        "foreign_install": foreign.path if foreign else "",
        "target": ctx.attr.target_name,
        "cache_entries": ctx.attr.cache_entries,
        "declared": {path: file.path for path, file in declared.items()},
        "declared_types": kinds,
        "build_type": variant.build_type,
        "sanitizer": variant.sanitizer,
        "static_cpp_runtime": _enabled(ctx, "static_cpp_runtime"),
        "copts": ctx.fragments.cpp.copts,
        "conlyopts": ctx.fragments.cpp.conlyopts,
        "cxxopts": ctx.fragments.cpp.cxxopts,
        "linkopts": ctx.fragments.cpp.linkopts,
        "separate_debug": _enabled(ctx, "separate_debug_info"),
        "jobs": int(ctx.var.get("forge_jobs", ctx.attr.jobs)),
    }, inputs, [install, manifest, debug, debug_manifest] + declared.values(), "CMakeBuild")
    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(ctx = ctx, cc_toolchain = cc_toolchain,
                                                        requested_features = ctx.features,
                                                        unsupported_features = ctx.disabled_features)
    libraries = []
    dynamic = []
    for library in descriptor.get("libraries", []):
        args = {"actions": ctx.actions, "cc_toolchain": cc_toolchain,
                "feature_configuration": feature_configuration,
                "alwayslink": library.get("alwayslink", False)}
        for key, parameter in [("static", "static_library"), ("pic_static", "pic_static_library"), ("shared", "dynamic_library")]:
            if library.get(key):
                args[parameter] = declared[library[key]]
                if key == "shared":
                    dynamic.append(declared[library[key]])
        libraries.append(cc_common.create_library_to_link(**args))
    export_root = install.dirname + "/" + ctx.label.name + ".exports"
    own_info = CcInfo(
        compilation_context = cc_common.create_compilation_context(
            headers = depset([declared[path] for path in descriptor.get("headers", [])]),
            includes = depset([export_root + "/" + _relative(path) for path in descriptor.get("includes", [])]),
            defines = depset(descriptor.get("defines", [])),
        ),
        linking_context = cc_common.create_linking_context(linker_inputs = depset([
            cc_common.create_linker_input(owner = ctx.label, libraries = depset(libraries),
                                          user_link_flags = depset(descriptor.get("linkopts", []))),
        ])),
    )
    dependencies = ctx.attr.deps + ctx.attr.data
    runfiles = ctx.runfiles(files = [install] + dynamic + ctx.files.data)
    for dep in dependencies:
        runfiles = runfiles.merge(dep[DefaultInfo].default_runfiles)
    debug_files = [dep[ErosDebugInfo].files for dep in dependencies if ErosDebugInfo in dep]
    debug_manifests = [dep[ErosDebugInfo].manifests for dep in dependencies if ErosDebugInfo in dep]
    all_debug_files = depset([debug], transitive = debug_files)
    all_debug_manifests = depset([debug_manifest], transitive = debug_manifests)
    entries = [struct(file = install, path = "")] + [
        struct(file = declared[path], path = path, explicit = True)
        for path in descriptor.get("runtime_files", [])
    ]
    manifests = [manifest]
    for dep in dependencies:
        if ErosInstallInfo in dep:
            entries += dep[ErosInstallInfo].entries
            manifests += dep[ErosInstallInfo].manifests
    return [
        DefaultInfo(files = depset([install, manifest] + declared.values()), runfiles = runfiles),
        cc_common.merge_cc_infos(cc_infos = [own_info] + [dep[CcInfo] for dep in ctx.attr.deps if CcInfo in dep]),
        ErosInstallInfo(entries = entries, manifests = manifests),
        ErosDebugInfo(files = all_debug_files, manifests = all_debug_manifests),
        OutputGroupInfo(eros_debug_info = depset(transitive = [all_debug_files, all_debug_manifests]),
                        install = depset([install]), binaries = depset([declared[p] for p in descriptor.get("binaries", [])])),
    ]

_cmake_attrs = _action_attrs()
_cmake_attrs.update({
    "cmake_lists": attr.label(allow_single_file = True),
    "srcs": attr.label_list(allow_files = True),
    "extra_srcs": attr.label_list(allow_files = True),
    "toolchain": attr.label(allow_single_file = True),
    "conan_deps": attr.label(providers = [ConanSnapshotInfo]),
    "foreign_install": attr.label(allow_single_file = True),
    "target_name": attr.string(),
    "exports_json": attr.string(default = "{}"),
    "cache_entries": attr.string_dict(),
    "deps": attr.label_list(providers = [CcInfo]),
    "data": attr.label_list(allow_files = True),
    "_driver": attr.label(default = Label("//bazel/tools:cmake_action.py"), allow_single_file = True),
    "_cc_toolchain": attr.label(default = Label("@bazel_tools//tools/cpp:current_cc_toolchain")),
})

cmake_build = rule(implementation = _cmake_build_impl, attrs = _cmake_attrs, fragments = ["cpp"],
                   toolchains = ["@bazel_tools//tools/cpp:toolchain_type"])

def legacy_exports(name, out_binary, out_static_libs, out_shared_libs, hdrs, includes, linkopts, exports):
    """Normalize the compatible basic macro arguments into one strict descriptor."""
    result = dict(exports or {})
    libraries = list(result.get("libraries", []))
    if not libraries:
        by_name = {}
        for filename in out_static_libs:
            key = filename.removeprefix("lib").removesuffix(".a")
            by_name[key] = {"name": key, "static": "lib/" + filename, "pic_static": "lib/" + filename}
        for filename in out_shared_libs:
            key = filename.removeprefix("lib").split(".so")[0]
            entry = by_name.get(key, {"name": key})
            entry["shared"] = "lib/" + filename
            by_name[key] = entry
        libraries = by_name.values()
    result["libraries"] = libraries
    if out_binary == None:
        out_binary = "" if libraries or exports != None else name
    if out_binary:
        result["binaries"] = list(result.get("binaries", [])) + ["bin/" + out_binary]
    if not result.get("headers") and hdrs:
        result["headers"] = [str(header) if str(header).startswith("include/") else "include/" + str(header).split(":")[-1].split("/")[-1] for header in hdrs]
    if includes != None:
        result["includes"] = includes
    elif "includes" not in result and result.get("headers"):
        result["includes"] = ["include"]
    result["linkopts"] = list(result.get("linkopts", [])) + linkopts
    return result

def cmake_conan_forge(name, conanfile, cmake_lists, srcs, lockfile, target_name = None,
                      out_binary = None, out_static_libs = [], out_shared_libs = [],
                      hdrs = None, includes = None, extra_srcs = [], exports = None,
                      linkopts = [], file_remote = [], local_recipes = [], remote_config = None,
                      cache_archive = None, jobs = 2, **kwargs):
    """Compatibility macro with a mandatory ordinary-build lockfile."""
    conan_install(
        name = name + "_conan",
        conanfile = conanfile,
        lockfile = lockfile,
        extra_srcs = extra_srcs,
        host_profile = conan_host_profile(),
        build_profile = conan_build_profile(),
        file_remote = file_remote,
        local_recipes = local_recipes,
        remote_config = remote_config,
        cache_archive = cache_archive,
        jobs = jobs,
        tags = kwargs.get("tags", []),
        features = kwargs.get("features", []),
        testonly = kwargs.get("testonly", False),
        target_compatible_with = kwargs.get("target_compatible_with", []),
    )
    descriptor = legacy_exports(target_name or name, out_binary, out_static_libs, out_shared_libs,
                                hdrs, includes, linkopts, exports)
    cmake_build(name = name, conan_deps = ":" + name + "_conan", cmake_lists = cmake_lists,
                srcs = srcs + (hdrs or []), extra_srcs = extra_srcs, target_name = target_name or "",
                toolchain = cmake_toolchain(), exports_json = json.encode(descriptor), jobs = jobs, **kwargs)
