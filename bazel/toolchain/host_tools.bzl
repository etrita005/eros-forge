"""Declare the actual controlled tools and their complete environment identity."""

def _host_tools_impl(ctx):
    ctx.watch(ctx.path(ctx.attr._probe))
    ctx.watch(ctx.path(ctx.attr._spec))
    python = ctx.which("python3")
    if not python:
        fail("Forge environment requires Python 3")
    conan = ctx.which("conan")
    if not conan:
        conan = ctx.path(ctx.os.environ.get("HOME", "") + "/.local/bin/conan")
    bazel = ctx.which("bazel")
    if not bazel:
        fail("Forge environment requires Bazel 9.0.0 in PATH")
    result = ctx.execute(
        [str(python), "-I", "-B", str(ctx.path(ctx.attr._probe)), "capture", "--spec", str(ctx.path(ctx.attr._spec)), "--repository", str(ctx.path(".")), "--conan", str(conan), "--bazel", str(bazel)],
        environment = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "LC_ALL": "C"},
        timeout = 600,
    )
    if result.return_code:
        fail(result.stdout + result.stderr)
    manifest = json.decode(ctx.read("env_manifest.json"))
    for identity in manifest["identities"]:
        if identity["kind"] == "tree":
            ctx.watch_tree(identity["path"])
        else:
            ctx.watch(identity["path"])

eros_host_tools_repo = repository_rule(
    implementation = _host_tools_impl,
    attrs = {
        "_probe": attr.label(default = Label("//bazel/toolchain:environment.py"), allow_single_file = True),
        "_spec": attr.label(default = Label("//bazel/toolchain:environment_spec.json"), allow_single_file = True),
    },
    environ = ["PATH", "HOME"],
    local = True,
    configure = True,
)

def _eros_host_tools_impl(module_ctx):
    eros_host_tools_repo(name = "eros_host_tools")

eros_host_tools = module_extension(implementation = _eros_host_tools_impl)
