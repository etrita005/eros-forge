"""An explicit, cacheable local environment-validation action."""

load("@eros_host_tools//:tools.bzl", "PYTHON")

def _validate_environment_impl(ctx):
    stamp = ctx.actions.declare_file(ctx.label.name + ".stamp")
    ctx.actions.run(
        executable = PYTHON,
        arguments = ["-I", "-B", ctx.file._probe.path, "validate", "--manifest", ctx.file.manifest.path, "--spec", ctx.file._spec.path, "--stamp", stamp.path],
        inputs = depset([ctx.file._probe, ctx.file._spec, ctx.file.manifest], transitive = [ctx.attr.tools[DefaultInfo].files]),
        outputs = [stamp],
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        execution_requirements = {"no-remote-exec": "1"},
        mnemonic = "ForgeEnvironmentValidation",
        progress_message = "Validating the installed Forge toolchain and SDK identity",
    )
    return [DefaultInfo(files = depset([stamp]))]

validate_environment = rule(
    implementation = _validate_environment_impl,
    attrs = {
        "manifest": attr.label(default = Label("@eros_host_tools//:env_manifest"), allow_single_file = True),
        "tools": attr.label(default = Label("@eros_host_tools//:all_tools")),
        "_probe": attr.label(default = Label("//bazel/toolchain:environment.py"), allow_single_file = True),
        "_spec": attr.label(default = Label("//bazel/toolchain:environment_spec.json"), allow_single_file = True),
    },
)
