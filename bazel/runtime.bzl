"""Native C++ adapters and a shared, data-aware runtime closure aspect."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@eros_host_tools//:tools.bzl", "PYTHON")
load("//bazel/config:validation.bzl", "VARIANT_ATTRS", "validate_configuration")
load("//bazel:providers.bzl", "ErosDebugInfo", "ErosInstallInfo")

RuntimeClosureInfo = provider(fields = ["entries", "manifests", "debug_files", "debug_manifests", "debug_binaries"])
_RuntimeMappingsInfo = provider(fields = ["entries", "complete", "debug_binaries"])

def _is_shared(file):
    return file.basename.endswith(".so") or ".so." in file.basename

def default_install_path(file, executable = False):
    if file.is_directory:
        return ""
    if executable:
        return "bin/" + file.basename
    if _is_shared(file):
        return "lib/" + file.basename
    return "share/" + file.basename

def _entry(file, path, key = None, explicit = False, dereference = False, implicit = False):
    return struct(file = file, path = path, key = key or file.path, explicit = explicit, dereference = dereference, implicit = implicit)

def _unique_entries(entries):
    # A published native file replaces its unprocessed runfile with the same key.
    result = {}
    for entry in entries:
        key = (entry.key, entry.path)
        previous = result.get(key)
        if previous == None or entry.file.path != entry.key or entry.explicit:
            result[key] = entry
    files = {}
    for entry in result.values():
        key = (entry.file.path, entry.path)
        previous = files.get(key)
        if previous == None or entry.explicit or (previous.implicit and not entry.implicit):
            files[key] = entry
    mapped_files = {entry.file.path: True for entry in files.values() if not entry.implicit}
    mapped_keys = {entry.key: True for entry in files.values() if not entry.implicit}
    return [entry for entry in files.values() if not entry.implicit or (entry.file.path not in mapped_files and entry.key not in mapped_keys)]

def _aspect_impl(target, ctx):
    entries = []
    manifests = []
    debug_files = []
    debug_manifests = []
    debug_binaries = []
    for name in ["deps", "data", "target", "conan_deps"]:
        if ctx.rule == None or not hasattr(ctx.rule.attr, name):
            continue
        value = getattr(ctx.rule.attr, name)
        children = value if type(value) == "list" else [value]
        for child in children:
            if child == None:
                continue
            if RuntimeClosureInfo not in child:
                if name == "data" and DefaultInfo in child:
                    entries.extend([_entry(file, default_install_path(file), explicit = True) for file in child[DefaultInfo].files.to_list()])
                continue
            info = child[RuntimeClosureInfo]
            if name == "conan_deps":
                debug_binaries.append(child[DefaultInfo].files)
                debug_files.append(info.debug_files)
                debug_manifests.append(info.debug_manifests)
                continue
            if name == "data":
                for entry in info.entries:
                    entries.append(_entry(entry.file, entry.path, entry.key, True, entry.dereference, entry.implicit))
            else:
                entries.extend(info.entries)
            manifests.extend(info.manifests)
            debug_files.append(info.debug_files)
            debug_manifests.append(info.debug_manifests)
            debug_binaries.append(info.debug_binaries)
    if _RuntimeMappingsInfo in target:
        published = target[_RuntimeMappingsInfo].entries
        replaced = {entry.key: True for entry in published}
        entries = [] if target[_RuntimeMappingsInfo].complete else [entry for entry in entries if entry.key not in replaced]
        entries.extend(published)
        debug_binaries.append(target[_RuntimeMappingsInfo].debug_binaries)
    elif ErosInstallInfo in target:
        for entry in target[ErosInstallInfo].entries:
            entries.append(_entry(entry.file, entry.path, explicit = not entry.file.is_directory))
    elif DefaultInfo in target:
        executable = target[DefaultInfo].files_to_run.executable
        if executable != None:
            entries.append(_entry(executable, default_install_path(executable, True)))
        for file in target[DefaultInfo].default_runfiles.files.to_list():
            if file != executable and not any([file.basename.endswith(suffix) for suffix in [".a", ".lo", ".o", ".h", ".hh", ".hpp", ".hxx", ".dwo", ".dwp"]]):
                entries.append(_entry(file, default_install_path(file), dereference = not file.is_source, implicit = True))
        if executable == None and CcInfo not in target:
            for file in target[DefaultInfo].files.to_list():
                entries.append(_entry(file, default_install_path(file)))
        elif executable == None:
            for file in target[DefaultInfo].files.to_list():
                if _is_shared(file):
                    entries.append(_entry(file, default_install_path(file)))
    if ErosInstallInfo in target:
        manifests.extend(target[ErosInstallInfo].manifests)
        debug_binaries.append(depset([entry.file for entry in target[ErosInstallInfo].entries]))
    if ErosDebugInfo in target:
        debug_files.append(target[ErosDebugInfo].files)
        debug_manifests.append(target[ErosDebugInfo].manifests)
    return [RuntimeClosureInfo(
        entries = _unique_entries(entries),
        manifests = depset(manifests).to_list(),
        debug_files = depset(transitive = debug_files),
        debug_manifests = depset(transitive = debug_manifests),
        debug_binaries = depset(transitive = debug_binaries),
    )]

runtime_closure = aspect(
    implementation = _aspect_impl,
    attr_aspects = ["deps", "data", "target", "conan_deps"],
)

def selected_runtime_entries(target):
    """Select actual runfiles, not every dynamic alternative offered by CcInfo."""
    if RuntimeClosureInfo not in target:
        return [_entry(file, default_install_path(file), explicit = True) for file in target[DefaultInfo].files.to_list()]
    info = target[RuntimeClosureInfo]
    selected = {}
    for file in target[DefaultInfo].default_runfiles.files.to_list() + target[DefaultInfo].files.to_list():
        selected[file.path] = True
    if target[DefaultInfo].files_to_run.executable != None:
        selected[target[DefaultInfo].files_to_run.executable.path] = True
    result = []
    for entry in info.entries:
        if entry.explicit or entry.key in selected or entry.file.path in selected or entry.file.is_directory:
            result.append(entry)
    return _unique_entries(result)

def _safe_path(path, allow_empty = False):
    if path == "" and allow_empty:
        return
    if not path or path.startswith("/") or "\\" in path or any([p in ["", ".", ".."] for p in path.split("/")]):
        fail("invalid/escaping private installation path: %r" % path)

def _install_map_impl(ctx):
    entries = []
    files = []
    runfiles = ctx.runfiles()
    for target, path in ctx.attr.files.items():
        mapped = target[DefaultInfo].files.to_list()
        if len(mapped) != 1:
            fail("%s: install mapping requires exactly one file/tree from %s, got %s" % (ctx.label, target.label, len(mapped)))
        _safe_path(path, mapped[0].is_directory)
        entries.append(_entry(mapped[0], path, explicit = True))
        files.extend(mapped)
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    for target in ctx.attr.deps:
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    return [
        DefaultInfo(files = depset(files), runfiles = runfiles.merge(ctx.runfiles(files = files))),
        ErosInstallInfo(entries = [struct(file = e.file, path = e.path) for e in entries], manifests = []),
        _RuntimeMappingsInfo(entries = entries, complete = False, debug_binaries = depset()),
    ]

eros_install_map = rule(
    implementation = _install_map_impl,
    attrs = {
        "files": attr.label_keyed_string_dict(allow_files = True),
        "deps": attr.label_list(),
    },
    doc = "Explicit files={label: private-relative destination}; directory labels map contents. deps carries plugin dependencies.",
)

def _debug_enabled(ctx):
    return "separate_debug_info" in ctx.features and "separate_debug_info" not in ctx.disabled_features

def _native_export_impl(ctx):
    variant = validate_configuration(ctx)
    target = ctx.attr.target
    native = target[DefaultInfo]
    executable = native.files_to_run.executable if ctx.attr.is_binary else None
    originals = [executable] if executable != None else (ctx.attr.shared_target[DefaultInfo].files.to_list() if ctx.attr.shared_target else [])
    entries = []
    outputs = []
    binaries = []
    symlinks = []
    dynamic_library = None
    for original in originals:
        basename = ctx.attr.install_name or (ctx.label.name if executable != None else original.basename)
        if "/" in basename or basename in ["", ".", ".."]:
            fail("install_name must be a basename: %r" % basename)
        if executable != None:
            published = ctx.actions.declare_file(ctx.label.name + ".elf")
            entries.append(_entry(published, "bin/" + basename, original.path))
            public = ctx.actions.declare_file(ctx.label.name)
        else:
            published = ctx.actions.declare_file(basename)
            dynamic_library = published
            entries.append(_entry(published, "lib/" + basename, original.path))
            if ctx.attr.soname and ctx.attr.soname != basename:
                soname = ctx.actions.declare_file(ctx.attr.soname)
                symlinks.append({"output": soname.path, "target": published.basename})
                outputs.append(soname)
                entries.append(_entry(soname, "lib/" + soname.basename, original.path + ":soname"))
                dynamic_library = soname
            if ctx.attr.link_name and ctx.attr.link_name not in [basename, ctx.attr.soname]:
                link = ctx.actions.declare_file(ctx.attr.link_name)
                symlinks.append({"output": link.path, "target": ctx.attr.soname or published.basename})
                outputs.append(link)
                entries.append(_entry(link, "lib/" + link.basename, original.path + ":link"))
        outputs.append(published)
        binaries.append({"source": original.path, "output": published.path})
    debug_dir = ctx.actions.declare_directory(ctx.label.name + ".debug")
    debug_manifest = ctx.actions.declare_file(ctx.label.name + ".debug_manifest.json")
    spec = ctx.actions.declare_file(ctx.label.name + ".native_spec.json")
    ctx.actions.write(spec, json.encode({
        "label": str(ctx.label),
        "preset": variant.preset,
        "separate_debug": _debug_enabled(ctx),
        "binaries": binaries,
        "symlinks": symlinks,
        "debug_dir": debug_dir.path,
        "debug_manifest": debug_manifest.path,
    }))
    ctx.actions.run(
        executable = PYTHON,
        arguments = [ctx.file._driver.path, "native", "--spec", spec.path, "--environment", ctx.file._env_manifest.path],
        inputs = depset(originals + [spec, ctx.file._driver, ctx.file._env_manifest], transitive = [ctx.attr._all_tools[DefaultInfo].files, ctx.attr._validator[DefaultInfo].files]),
        outputs = outputs + [debug_dir, debug_manifest],
        mnemonic = "ErosNativePublish",
        progress_message = "Publishing native runtime/debug artifacts %s (%s)" % (ctx.label, variant.preset),
        env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        execution_requirements = {"no-remote-exec": "1"},
    )
    debug_binaries = depset([file for file in outputs if file.basename.endswith(".elf") or _is_shared(file)])
    if ctx.attr.is_binary:
        runtime_tree = ctx.actions.declare_directory(ctx.label.name + ".runtime")
        layout_spec = ctx.actions.declare_file(ctx.label.name + ".layout_spec.json")
        runtime_entries = [entry for entry in selected_runtime_entries(target) if entry.key != executable.path]
        runtime_entries.extend(entries)
        runtime_entries = _unique_entries(runtime_entries)
        ctx.actions.write(layout_spec, json.encode({
            "label": str(ctx.label), "package": ctx.label.name, "preset": variant.preset,
            "sanitizer": variant.sanitizer,
            "entries": [{"source": entry.file.path, "destination": entry.path, "explicit": entry.explicit, "dereference": entry.dereference} for entry in runtime_entries],
            "output": runtime_tree.path, "executable": public.path,
            "executable_target": runtime_tree.basename + "/bin/" + (ctx.attr.install_name or ctx.label.name),
        }))
        ctx.actions.run(
            executable = PYTHON,
            arguments = [ctx.file._driver.path, "layout", "--spec", layout_spec.path, "--environment", ctx.file._env_manifest.path],
            inputs = depset([entry.file for entry in runtime_entries] + [layout_spec, ctx.file._driver, ctx.file._env_manifest], transitive = [ctx.attr._all_tools[DefaultInfo].files, ctx.attr._validator[DefaultInfo].files]),
            outputs = [runtime_tree, public], mnemonic = "ErosRunfilesLayout",
            progress_message = "Materializing checked runtime/runfiles layout %s" % ctx.label,
            env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            execution_requirements = {"no-remote-exec": "1"},
        )
        entries = [_entry(runtime_tree, "", explicit = True)]
        default_outputs = [public, runtime_tree]
    else:
        default_outputs = native.files.to_list() + outputs
    runfiles = native.default_runfiles.merge(ctx.runfiles(files = default_outputs))
    transitive_debug = [target[RuntimeClosureInfo].debug_files]
    transitive_manifests = [target[RuntimeClosureInfo].debug_manifests]
    if _debug_enabled(ctx) and binaries:
        transitive_debug.append(depset([debug_dir]))
        transitive_manifests.append(depset([debug_manifest]))
    debug_files = depset(transitive = transitive_debug)
    debug_manifests = depset(transitive = transitive_manifests)
    providers = [
        DefaultInfo(files = depset(default_outputs), executable = public if ctx.attr.is_binary else None, runfiles = runfiles),
        ErosInstallInfo(entries = [struct(file = e.file, path = e.path) for e in entries], manifests = []),
        _RuntimeMappingsInfo(entries = entries, complete = ctx.attr.is_binary, debug_binaries = debug_binaries),
        ErosDebugInfo(files = debug_files, manifests = debug_manifests),
        OutputGroupInfo(eros_debug_info = depset(transitive = [debug_files, debug_manifests]), eros_runtime_files = depset(outputs)),
    ]
    if CcInfo in target:
        if ctx.attr.is_binary or dynamic_library == None:
            providers.append(target[CcInfo])
        else:
            cc_toolchain = find_cpp_toolchain(ctx)
            features = cc_common.configure_features(ctx = ctx, cc_toolchain = cc_toolchain, requested_features = ctx.features, unsupported_features = ctx.disabled_features)
            own_libraries = []
            own_flags = []
            own_inputs = []
            transitive = []
            for linker_input in target[CcInfo].linking_context.linker_inputs.to_list():
                if linker_input.owner == target.label:
                    own_flags.extend(linker_input.user_link_flags)
                    own_inputs.extend(linker_input.additional_inputs)
                    for library in linker_input.libraries:
                        static_library = None
                        pic_static_library = None
                        if library.static_library:
                            static_library = ctx.actions.declare_file(ctx.label.name + ".static.a")
                            ctx.actions.symlink(output = static_library, target_file = library.static_library)
                        if library.pic_static_library:
                            pic_static_library = ctx.actions.declare_file(ctx.label.name + ".pic.a")
                            ctx.actions.symlink(output = pic_static_library, target_file = library.pic_static_library)
                        exported = cc_common.create_library_to_link(
                            actions = ctx.actions, cc_toolchain = cc_toolchain, feature_configuration = features,
                            static_library = static_library, pic_static_library = pic_static_library,
                            dynamic_library = dynamic_library, alwayslink = ctx.attr.alwayslink,
                        )
                        own_libraries.append(exported)
                        # Bazel loads native shared libraries from sibling
                        # _solib directories. Their own indirect dependencies
                        # cannot rely on the executable's non-transitive RUNPATH.
                        own_flags.append("-Wl,-rpath,$ORIGIN/../" + exported.dynamic_library.dirname.split("/")[-1])
                else:
                    transitive.append(linker_input)
            own = cc_common.create_linker_input(owner = ctx.label, libraries = depset(own_libraries), user_link_flags = depset(own_flags), additional_inputs = depset(own_inputs))
            providers.append(CcInfo(compilation_context = target[CcInfo].compilation_context,
                                    linking_context = cc_common.create_linking_context(linker_inputs = depset([own] + transitive, order = "topological"))))
    return providers

_EXPORT_ATTRS = dict(VARIANT_ATTRS, **{
    "target": attr.label(mandatory = True, aspects = [runtime_closure]),
    "is_binary": attr.bool(),
    "install_name": attr.string(),
    "soname": attr.string(),
    "link_name": attr.string(),
    "shared_target": attr.label(),
    "alwayslink": attr.bool(),
    "_cc_toolchain": attr.label(default = Label("@bazel_tools//tools/cpp:current_cc_toolchain")),
    "_driver": attr.label(default = Label("//bazel/packaging:driver.py"), allow_single_file = True),
    "_env_manifest": attr.label(default = Label("@eros_host_tools//:env_manifest"), allow_single_file = True),
    "_all_tools": attr.label(default = Label("@eros_host_tools//:all_tools")),
    "_validator": attr.label(default = Label("//bazel/toolchain:validate_environment")),
})

_native_binary = rule(implementation = _native_export_impl, attrs = _EXPORT_ATTRS, executable = True, fragments = ["cpp"])
_native_library = rule(implementation = _native_export_impl, attrs = _EXPORT_ATTRS, fragments = ["cpp"], toolchains = ["@bazel_tools//tools/cpp:toolchain_type"])

def _public_args(kwargs):
    result = {}
    for name in ["visibility", "testonly", "tags", "target_compatible_with", "features"]:
        if name in kwargs:
            result[name] = kwargs[name]
    return result

def eros_cc_binary(name, install_name = "", **kwargs):
    """cc_binary with real executable forwarding, private RUNPATH, and symbols."""
    public_args = _public_args(kwargs)
    native_args = dict(kwargs)
    native_args["visibility"] = ["//visibility:private"]
    native_args["copts"] = kwargs.get("copts", []) + ["-g"]
    native_args["linkopts"] = kwargs.get("linkopts", []) + ["-Wl,--build-id=sha1", "-Wl,-rpath,$$ORIGIN/../lib", "-Wl,-rpath,$$ORIGIN"]
    cc_binary(name = name + "_cc", **native_args)
    _native_binary(name = name, target = ":" + name + "_cc", is_binary = True, install_name = install_name, **public_args)

def eros_cc_library(name, install_name = "", soname = "", link_name = "", **kwargs):
    """cc_library preserving its CcInfo; versioned shared install names optional."""
    public_args = _public_args(kwargs)
    native_args = dict(kwargs)
    native_args["visibility"] = ["//visibility:private"]
    native_args["copts"] = kwargs.get("copts", []) + ["-g"]
    native_args["linkopts"] = kwargs.get("linkopts", []) + ["-Wl,--build-id=sha1", "-Wl,-rpath,$$ORIGIN/../lib", "-Wl,-rpath,$$ORIGIN"]
    shared = kwargs.get("linkstatic", False) != True
    install_name = install_name or ("lib" + name.split("/")[-1] + ".so" if shared else "")
    soname = soname or install_name
    if shared:
        # A separate native shared link gives each ELF its own DT_NEEDED and
        # keeps SONAME flags local instead of leaking them through CcInfo.
        native_args["linkstatic"] = True
        native_args["alwayslink"] = True
    cc_library(name = name + "_cc", **native_args)
    if shared:
        cc_binary(name = name + "_shared.so", deps = [":" + name + "_cc"], linkshared = True, linkstatic = False,
                  linkopts = ["-Wl,--build-id=sha1", "-Wl,-rpath,$$ORIGIN/../lib", "-Wl,-rpath,$$ORIGIN"] + (["-Wl,-soname," + soname] if soname else []),
                  **dict(public_args, visibility = ["//visibility:private"]))
    _native_library(name = name, target = ":" + name + "_cc", shared_target = ":" + name + "_shared.so" if shared else None,
                    install_name = install_name, soname = soname, link_name = link_name, alwayslink = kwargs.get("alwayslink", False), **public_args)
