"""Checked private runtime archives, Debian packages, and real split builds."""

load("//bazel/config:validation.bzl", "VARIANT_ATTRS", "validate_configuration")
load("//bazel:providers.bzl", "ErosDebugInfo")
load("//bazel:runtime.bzl", "RuntimeClosureInfo", "default_install_path", "runtime_closure", "selected_runtime_entries")
load("@eros_host_tools//:tools.bzl", "PYTHON")

ErosPackageInfo = provider(fields = ["payload", "manifest"])

def _driver_action(ctx, mode, spec, inputs, outputs, mnemonic, environment = True, version_env = False):
    spec_file = ctx.actions.declare_file(outputs[0].basename + ".spec.json")
    ctx.actions.write(spec_file, json.encode(spec))
    arguments = [ctx.file._driver.path, mode, "--spec", spec_file.path]
    direct = [spec_file, ctx.file._driver]
    if environment:
        arguments.extend(["--environment", ctx.file._env_manifest.path])
        direct.append(ctx.file._env_manifest)
    ctx.actions.run(
        executable = PYTHON,
        arguments = arguments,
        inputs = depset(direct, transitive = inputs + [ctx.attr._all_tools[DefaultInfo].files, ctx.attr._validator[DefaultInfo].files]),
        outputs = outputs,
        mnemonic = mnemonic,
        progress_message = "%s %s" % (mnemonic, ctx.label),
        env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        use_default_shell_env = version_env,
        execution_requirements = {"no-remote-exec": "1"},
    )

def _export_impl(ctx):
    variant = validate_configuration(ctx)
    mappings = []
    inputs = []
    provenance = []
    debug_files = []
    debug_manifests = []
    runtime_mappings = []
    debug_only = ctx.attr.output_group == "eros_debug_info"
    for target in ctx.attr.srcs:
        info = target[RuntimeClosureInfo] if RuntimeClosureInfo in target else None
        if ctx.attr.output_group:
            if OutputGroupInfo not in target or not hasattr(target[OutputGroupInfo], ctx.attr.output_group):
                fail("%s: %s has no output group %r" % (ctx.label, target.label, ctx.attr.output_group))
            group_files = getattr(target[OutputGroupInfo], ctx.attr.output_group)
            if debug_only and info != None:
                group_files = depset(transitive = [group_files, info.debug_files, info.debug_manifests])
            for file in group_files.to_list():
                destination = "symbols/%s/%s" % (len(mappings), file.basename) if debug_only else default_install_path(file)
                mappings.append({"source": file.path, "destination": destination, "explicit": True})
                inputs.append(file)
            if debug_only:
                for entry in selected_runtime_entries(target):
                    runtime_mappings.append({"source": entry.file.path, "destination": entry.path})
                    inputs.append(entry.file)
        else:
            for entry in selected_runtime_entries(target):
                mappings.append({"source": entry.file.path, "destination": entry.path, "dereference": entry.dereference, "explicit": entry.explicit})
                inputs.append(entry.file)
        if info != None:
            provenance.extend(info.manifests)
            debug_files.append(info.debug_files)
            debug_manifests.append(info.debug_manifests)
            inputs.extend(info.debug_binaries.to_list())
    debug = depset(transitive = debug_files)
    manifests = depset(transitive = debug_manifests)
    package = ctx.attr.package
    output = ctx.outputs.out or ctx.actions.declare_file(ctx.label.name + ".tar.gz")
    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    debug_entries = []
    if ctx.attr.test_package:
        for i, file in enumerate(debug.to_list()):
            debug_entries.append({"source": file.path, "destination": "debug/%s/%s" % (i, file.basename)})
            inputs.append(file)
    inputs.extend(provenance + manifests.to_list() + debug.to_list())
    _driver_action(ctx, "export", {
        "label": str(ctx.label),
        "package": package,
        "package_dir": ctx.attr.package_dir,
        "preset": variant.preset,
        "sanitizer": variant.sanitizer,
        "entries": mappings,
        "manifests": depset(provenance).to_list() and [f.path for f in depset(provenance).to_list()],
        "debug_manifests": [f.path for f in manifests.to_list()],
        "debug_entries": debug_entries,
        "test_package": ctx.attr.test_package,
        "debug_only": debug_only,
        "separate_debug": "separate_debug_info" in ctx.features and "separate_debug_info" not in ctx.disabled_features,
        "runtime_entries": runtime_mappings,
        "entry_points": ctx.attr.entry_points,
        "output": output.path,
        "manifest": manifest.path,
    }, [depset(inputs)], [output, manifest], "ErosRuntimeExport")
    return [
        DefaultInfo(files = depset([output])),
        ErosPackageInfo(payload = output, manifest = manifest),
        ErosDebugInfo(files = debug, manifests = manifests),
        OutputGroupInfo(eros_manifest = depset([manifest]), eros_debug_info = depset(transitive = [debug, manifests])),
    ]

_COMMON_ATTRS = {
    "_driver": attr.label(default = Label("//bazel/packaging:driver.py"), allow_single_file = True),
    "_env_manifest": attr.label(default = Label("@eros_host_tools//:env_manifest"), allow_single_file = True),
    "_all_tools": attr.label(default = Label("@eros_host_tools//:all_tools")),
    "_validator": attr.label(default = Label("//bazel/toolchain:validate_environment")),
}

_runtime_export = rule(
    implementation = _export_impl,
    attrs = dict(VARIANT_ATTRS, **dict(_COMMON_ATTRS, **{
        "srcs": attr.label_list(allow_files = True, aspects = [runtime_closure]),
        "package": attr.string(mandatory = True),
        "package_dir": attr.string(),
        "output_group": attr.string(),
        "out": attr.output(),
        "test_package": attr.bool(),
        "entry_points": attr.string_list(),
    })),
    fragments = ["cpp"],
)

def pkg_eros_tar(name, srcs = [], output_group = "", package_dir = None, package = "", out = None, **kwargs):
    """Export the selected runtime closure below /opt/eros/<package> by default."""
    package = package or name
    _runtime_export(name = name, srcs = srcs, output_group = output_group, package = package,
                    package_dir = package_dir if package_dir != None else "/opt/eros/" + package, out = out, **kwargs)

def eros_test_package(name, srcs = [], package = "", entry_points = [], out = None, **kwargs):
    """CI export; builds and validates but never executes a target program."""
    _runtime_export(name = name, srcs = srcs, package = package or name, package_dir = "",
                    entry_points = entry_points, test_package = True, out = out, **kwargs)

def _payload(target, owner):
    if ErosPackageInfo in target:
        return target[ErosPackageInfo].payload
    files = target[DefaultInfo].files.to_list()
    if len(files) != 1:
        fail("%s: data must provide exactly one tar payload (got %s from %s)" % (owner, len(files), target.label))
    return files[0]

def _deb_spec(ctx, payload, output, manifest, architecture, preset):
    result = {
        "label": str(ctx.label), "data": payload.path, "output": output.path, "manifest": manifest.path,
        "package": ctx.attr.package, "version": ctx.attr.version, "define_version": ctx.var.get("DEB_VERSION", ""),
        "architecture": architecture, "preset": preset,
        "maintainer": ctx.attr.maintainer, "description": ctx.attr.description,
        "section": ctx.attr.section, "priority": ctx.attr.priority, "homepage": ctx.attr.homepage,
    }
    for name in ["depends", "predepends", "recommends", "suggests", "conflicts", "breaks", "replaces", "provides"]:
        result[name] = getattr(ctx.attr, name)
    result["scripts"] = {name: getattr(ctx.file, name).path for name in ["preinst", "postinst", "prerm", "postrm", "conffiles"] if getattr(ctx.file, name) != None}
    return result

def _scripts(ctx):
    return [getattr(ctx.file, name) for name in ["preinst", "postinst", "prerm", "postrm", "conffiles"] if getattr(ctx.file, name) != None]

def _deb_impl(ctx):
    variant = validate_configuration(ctx)
    payload = _payload(ctx.attr.data, ctx.label)
    output = ctx.outputs.out or ctx.actions.declare_file(ctx.label.name + ".deb")
    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    _driver_action(ctx, "deb", _deb_spec(ctx, payload, output, manifest, ctx.attr.architecture, variant.preset),
                   [depset([payload] + _scripts(ctx))], [output, manifest], "ErosDeb", environment = False, version_env = True)
    debug = ctx.attr.data[ErosDebugInfo] if ErosDebugInfo in ctx.attr.data else ErosDebugInfo(files = depset(), manifests = depset())
    return [DefaultInfo(files = depset([output])), ErosPackageInfo(payload = output, manifest = manifest), debug,
            OutputGroupInfo(eros_manifest = depset([manifest]), eros_debug_info = depset(transitive = [debug.files, debug.manifests]))]

_METADATA_ATTRS = {
    "package": attr.string(mandatory = True), "version": attr.string(), "architecture": attr.string(),
    "maintainer": attr.string(default = "EROS maintainers <maintainers@eros.invalid>"),
    "description": attr.string(default = "EROS private runtime package"),
    "section": attr.string(default = "misc"), "priority": attr.string(default = "optional"), "homepage": attr.string(),
    "depends": attr.string_list(), "predepends": attr.string_list(), "recommends": attr.string_list(),
    "suggests": attr.string_list(), "conflicts": attr.string_list(), "breaks": attr.string_list(),
    "replaces": attr.string_list(), "provides": attr.string_list(),
    "preinst": attr.label(allow_single_file = True), "postinst": attr.label(allow_single_file = True),
    "prerm": attr.label(allow_single_file = True), "postrm": attr.label(allow_single_file = True),
    "conffiles": attr.label(allow_single_file = True),
}

_pkg_deb = rule(
    implementation = _deb_impl,
    attrs = dict(VARIANT_ATTRS, **dict(_COMMON_ATTRS, **dict(_METADATA_ATTRS, **{
        "data": attr.label(mandatory = True, allow_files = True), "out": attr.output(),
    }))),
    fragments = ["cpp"],
)

def _auto_architecture():
    return select({
        Label("@platforms//cpu:aarch64"): "arm64",
        Label("@platforms//cpu:x86_64"): "amd64",
    }, no_match_error = "Forge Debian architecture mapping supports only aarch64->arm64 and x86_64->amd64; unknown CPU cannot default to all")

def _package_name(name, package, package_name):
    if package and package_name and package != package_name:
        fail("%s: conflicting package=%r and package_name=%r" % (name, package, package_name))
    return package or package_name or name

def pkg_eros_deb(name, data, package = "", package_name = "", architecture = None, **kwargs):
    _pkg_deb(name = name, data = data, package = _package_name(name, package, package_name),
             architecture = architecture if architecture != None else _auto_architecture(), **kwargs)

_PRESET_SETTING = str(Label("//bazel/config:preset"))

def _split_impl(settings, attr):
    result = {}
    for preset in attr.presets:
        result[preset] = {
            "//command_line_option:platforms": [str(Label("//bazel/toolchain:" + preset + "_platform"))],
            _PRESET_SETTING: preset,
        }
    return result

_presets_transition = transition(
    implementation = _split_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms", _PRESET_SETTING],
)

def _multiarch_impl(ctx):
    validate_configuration(ctx)
    outputs = []
    manifests = []
    debug_files = []
    debug_manifests = []
    for preset, target in ctx.split_attr.data.items():
        payload = _payload(target, "%s branch %s" % (ctx.label, preset))
        output = ctx.actions.declare_file(ctx.label.name + "." + preset + ".deb")
        manifest = ctx.actions.declare_file(ctx.label.name + "." + preset + ".manifest.json")
        architecture = "amd64" if preset == "linux_x86_64" else "arm64"
        _driver_action(ctx, "deb", _deb_spec(ctx, payload, output, manifest, architecture, preset),
                       [depset([payload] + _scripts(ctx))], [output, manifest], "ErosDebMultiarch", environment = False, version_env = True)
        outputs.append(output)
        manifests.append(manifest)
        if ErosDebugInfo in target:
            debug_files.append(target[ErosDebugInfo].files)
            debug_manifests.append(target[ErosDebugInfo].manifests)
    debug = ErosDebugInfo(files = depset(transitive = debug_files), manifests = depset(transitive = debug_manifests))
    return [DefaultInfo(files = depset(outputs)), debug,
            OutputGroupInfo(eros_manifest = depset(manifests), eros_debug_info = depset(transitive = [debug.files, debug.manifests]))]

_pkg_multiarch = rule(
    implementation = _multiarch_impl,
    attrs = dict(VARIANT_ATTRS, **dict(_COMMON_ATTRS, **dict(_METADATA_ATTRS, **{
        "data": attr.label(mandatory = True, cfg = _presets_transition, allow_files = True),
        "presets": attr.string_list(mandatory = True),
        "_allowlist_function_transition": attr.label(default = Label("@bazel_tools//tools/allowlists/function_transition_allowlist")),
    }))),
    fragments = ["cpp"],
)

def pkg_eros_deb_multiarch(name, data, architectures = ["amd64", "arm64"], presets = None, package = "", package_name = "", **kwargs):
    if presets == None:
        aliases = {"amd64": "linux_x86_64", "x86_64": "linux_x86_64", "arm64": "linux_x86_64_cross_arm64" if "amd64" in architectures or "x86_64" in architectures else "linux_arm64", "arm64_cross": "linux_arm64_cross_arm64"}
        presets = []
        for architecture in architectures:
            if architecture not in aliases:
                fail("%s: unsupported multiarch branch %r; use explicit presets for supported toolchains" % (name, architecture))
            presets.append(aliases[architecture])
    allowed = ["linux_x86_64", "linux_arm64", "linux_x86_64_cross_arm64", "linux_arm64_cross_arm64"]
    if not presets or len(depset(presets).to_list()) != len(presets):
        fail("%s: multiarch requires nonempty distinct preset branches" % name)
    for preset in presets:
        if preset not in allowed:
            fail("%s: unsupported multiarch preset branch %r" % (name, preset))
    _pkg_multiarch(name = name, data = data, package = _package_name(name, package, package_name), presets = presets, **kwargs)
