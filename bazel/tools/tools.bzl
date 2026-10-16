"""Executable maintenance entry point, intentionally not a build action."""

load("//bazel/config:variants.bzl", "conan_build_profile", "conan_host_profile")

def _runfile(ctx, file):
    return file.short_path[3:] if file.short_path.startswith("../") else ctx.workspace_name + "/" + file.short_path

def _lock_update_tool_impl(ctx):
    executable = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.write(executable, """#!/bin/sh
set -eu
root="${RUNFILES_DIR:-$0.runfiles}"
exec /usr/bin/python3 -B -s "$root/%s" --environment "$root/%s" --host-profile "$root/%s" --build-profile "$root/%s" "$@"
""" % (_runfile(ctx, ctx.file._script), _runfile(ctx, ctx.file._environment),
         _runfile(ctx, ctx.file.host_profile), _runfile(ctx, ctx.file.build_profile)), is_executable = True)
    return [DefaultInfo(executable = executable, runfiles = ctx.runfiles(
        files = [ctx.file._script, ctx.file._common, ctx.file._environment, ctx.file.host_profile, ctx.file.build_profile],
        transitive_files = ctx.attr._tools[DefaultInfo].files,
    ))]

_lock_update_tool = rule(implementation = _lock_update_tool_impl, executable = True, attrs = {
    "host_profile": attr.label(mandatory = True, allow_single_file = True),
    "build_profile": attr.label(mandatory = True, allow_single_file = True),
    "_script": attr.label(default = Label("//bazel/tools:conan_lock_update.py"), allow_single_file = True),
    "_common": attr.label(default = Label("//bazel/tools:action_common.py"), allow_single_file = True),
    "_environment": attr.label(default = Label("@eros_host_tools//:env_manifest"), allow_single_file = True),
    "_tools": attr.label(default = Label("@eros_host_tools//:all_tools")),
})

def lock_update_tool(name):
    _lock_update_tool(name = name, host_profile = conan_host_profile(), build_profile = conan_build_profile())
