# Copyright (c) 2024 EROS Project
# deb.bzl - EROS Debian package build rules
#
# This module provides a simplified way to build deb packages for EROS projects
# with automatic architecture detection based on Bazel's target platform.
#
# Usage:
#   load("@eros_forge//bazel:deb.bzl", "pkg_eros_deb")
#
#   pkg_eros_deb(
#       name = "my_package_deb",
#       package_name = "my-package",
#       description = "My package description",
#       data = ":my_data_tar",
#       maintainer = "Team <team@example.com>",
#       version = "1.0.0",  # Optional; see version priority below
#   )
#
# Then build with (the architecture is auto-selected from the target platform):
#   bazel build --config=linux_x86_64 //:my_package_deb   # -> amd64 deb
#   bazel build --config=linux_arm64  //:my_package_deb   # -> arm64 deb
#
# Version priority (highest first):
#   1. The `version` attribute (explicit)
#   2. The DEB_VERSION environment variable (requires the bazelrc
#      `build --action_env=DEB_VERSION` that Forge ships)
#   3. `--define=DEB_VERSION=x.x.x`
#   4. The default "0.1.0"
#
# Note: the env-var path is not part of Bazel's action cache key, so changing
# DEB_VERSION alone may not re-trigger the build. For deterministic, cache-correct
# versioning prefer `--define=DEB_VERSION=x.x.x` (a define change invalidates the
# configuration) or pass `version = ...` explicitly.

load("@rules_pkg//pkg:deb.bzl", "pkg_deb")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def pkg_eros_tar(
        name,
        srcs,
        output_group = None,
        package_dir = None,
        extension = "tar.gz",
        mode = "0755",
        strip_prefix = ".",
        modes = None,
        owner = None,
        owners = None,
        ownername = None,
        ownernames = None,
        empty_dirs = None,
        empty_files = None,
        symlinks = None,
        remap_paths = None,
        deps = None,
        **kwargs):
    """Create a pkg_tar with automatic filegroup for output_group extraction.

    This macro combines filegroup (for output_group extraction) and pkg_tar into a single call.

    Args:
        name: Name of the pkg_tar rule
        srcs: Source labels to include (will be wrapped in a filegroup with output_group)
        output_group: The output_group to extract from srcs (e.g., "dynamic_library").
                      If None or empty, no output_group filtering is applied.
        package_dir: Destination directory in the package
        extension: Archive extension (default: "tar.gz")
        mode: File mode (default: "0755")
        strip_prefix: Prefix to strip from paths (default: ".")
        modes: Dict of path -> mode to apply to specific files
        owner: Default owner (uid:gid) for all files
        owners: Dict of path -> owner for specific files
        ownername: Default owner name for all files
        ownernames: Dict of path -> owner name for specific files
        empty_dirs: List of empty directories to create
        empty_files: List of empty files to create
        symlinks: Dict of link -> target for symlinks
        remap_paths: Dict of path -> new_path for remapping
        deps: Additional dependencies
        **kwargs: Additional arguments passed to pkg_tar
    """

    # Create internal filegroup for output_group extraction
    filegroup_name = "_" + name + "_filegroup"
    filegroup_args = {
        "name": filegroup_name,
        "srcs": srcs,
        "visibility": ["//visibility:private"],
    }
    if output_group:
        filegroup_args["output_group"] = output_group
    native.filegroup(**filegroup_args)

    # Build pkg_tar arguments
    pkg_tar_args = {
        "name": name,
        "srcs": [":" + filegroup_name],
        "extension": extension,
        "strip_prefix": strip_prefix,
        "visibility": ["//visibility:private"],
    }

    if package_dir:
        pkg_tar_args["package_dir"] = package_dir
    if mode:
        pkg_tar_args["mode"] = mode
    if modes:
        pkg_tar_args["modes"] = modes
    if owner:
        pkg_tar_args["owner"] = owner
    if owners:
        pkg_tar_args["owners"] = owners
    if ownername:
        pkg_tar_args["ownername"] = ownername
    if ownernames:
        pkg_tar_args["ownernames"] = ownernames
    if empty_dirs:
        pkg_tar_args["empty_dirs"] = empty_dirs
    if empty_files:
        pkg_tar_args["empty_files"] = empty_files
    if symlinks:
        pkg_tar_args["symlinks"] = symlinks
    if remap_paths:
        pkg_tar_args["remap_paths"] = remap_paths
    if deps:
        pkg_tar_args["deps"] = deps

    pkg_tar_args.update(kwargs)

    pkg_tar(**pkg_tar_args)

def _eros_deb_version_impl(ctx):
    """Generate a version file for a deb package.

    Version resolution (highest priority first):
      1. ctx.attr.version (explicit attribute)
      2. $DEB_VERSION action environment variable
         (made available by the bazelrc `build --action_env=DEB_VERSION`)
      3. --define=DEB_VERSION=...
      4. "0.1.0"

    The env var is read inside the action (Bazel 9 removed analysis-time
    ctx.os.environ for regular rules), so `use_default_shell_env = True` is
    required for the action to see the inherited DEB_VERSION.
    """
    output = ctx.actions.declare_file(ctx.attr.name + ".txt")

    # Analysis-time values passed as action arguments.
    attr_version = ctx.attr.version
    define_version = ctx.var.get("DEB_VERSION", "")

    ctx.actions.run_shell(
        outputs = [output],
        arguments = [attr_version, define_version, output.path],
        command = """set -eu
ATTR_VERSION="$1"
DEFINE_VERSION="$2"
OUTPUT="$3"
if [ -n "$ATTR_VERSION" ]; then
    VERSION="$ATTR_VERSION"
elif [ -n "${DEB_VERSION:-}" ]; then
    VERSION="$DEB_VERSION"
elif [ -n "$DEFINE_VERSION" ]; then
    VERSION="$DEFINE_VERSION"
else
    VERSION="0.1.0"
fi
printf '%s' "$VERSION" > "$OUTPUT"
""",
        mnemonic = "ErosDebVersion",
        progress_message = "Generating deb version for {}".format(ctx.attr.name),
        use_default_shell_env = True,
    )

    return [DefaultInfo(files = depset([output]))]

eros_deb_version = rule(
    implementation = _eros_deb_version_impl,
    attrs = {
        "version": attr.string(
            doc = "Default version string. Priority: this attribute > $DEB_VERSION env > --define=DEB_VERSION > \"0.1.0\".",
        ),
    },
    doc = "Generates a version file for a deb package, honoring the DEB_VERSION " +
          "environment variable (via --action_env=DEB_VERSION) and --define=DEB_VERSION.",
)

# Architecture auto-detection from the target platform's cpu constraint. This
# produces a SINGLE pkg_deb target (no per-arch _amd64/_arm64 noise in
# `bazel query //...`). The glibc constraint is intentionally not consulted:
# deb architecture is determined by CPU, not by the libc variant.
def _eros_deb_architecture(architecture):
    if architecture:
        return architecture
    return select({
        "@platforms//cpu:x86_64": "amd64",
        "@platforms//cpu:arm64": "arm64",
        "//conditions:default": "all",
    })

def _eros_deb_common_args(
        package_name,
        data,
        description,
        maintainer,
        version_label,
        homepage,
        section,
        priority,
        preinst,
        postinst,
        prerm,
        postrm,
        conffiles,
        depends,
        suggests,
        enhances,
        breaks,
        conflicts,
        replaces,
        provides,
        recommends,
        kwargs):
    """Return the kwargs dict shared by every pkg_deb target this macro emits."""
    args = {
        "package": package_name,
        "data": data,
        "description": description,
        "maintainer": maintainer,
        "homepage": homepage,
        "section": section,
        "priority": priority,
        "version_file": version_label,
        "preinst": preinst,
        "postinst": postinst,
        "prerm": prerm,
        "postrm": postrm,
        "conffiles": conffiles,
        "depends": depends,
        "suggests": suggests,
        "enhances": enhances,
        "breaks": breaks,
        "conflicts": conflicts,
        "replaces": replaces,
        "provides": provides,
        "recommends": recommends,
    }
    args.update(kwargs)
    return args

def pkg_eros_deb(
        name,
        package_name,
        data,
        description,
        maintainer,
        version = None,
        architecture = None,
        homepage = "https://example.com",
        section = "libs",
        priority = "optional",
        preinst = None,
        postinst = None,
        prerm = None,
        postrm = None,
        conffiles = None,
        depends = None,
        suggests = None,
        enhances = None,
        breaks = None,
        conflicts = None,
        replaces = None,
        provides = None,
        recommends = None,
        **kwargs):
    """Create a deb package with automatic architecture detection.

    This macro emits a SINGLE pkg_deb target whose `architecture` is selected
    from the target platform's cpu constraint (amd64 on x86_64, arm64 on arm64).
    This keeps `bazel query //...` clean (no extra _amd64/_arm64 targets) while
    still producing the correct architecture for the configured platform.

    To build debs for multiple architectures from one workspace, use
    :func:`pkg_eros_deb_multiarch` instead, which emits explicit per-arch targets.

    Args:
        name: Name of the rule
        package_name: Name of the debian package (e.g., "my-package")
        data: Label of the pkg_tar target containing the package data
        description: Package description
        maintainer: Package maintainer (e.g., "Team <team@example.com>")
        version: Default version string. Can be overridden by the DEB_VERSION env
            var or --define=DEB_VERSION=xxx (see version priority in deb.bzl).
        architecture: Explicit debian architecture (e.g., "amd64", "arm64",
            "all"). If None (default), the architecture is auto-selected from the
            target platform's cpu constraint.
        homepage: Package homepage URL
        section: Debian section (default: "libs")
        priority: Package priority (default: "optional")
        preinst: Optional pre-installation script
        postinst: Optional post-installation script
        prerm: Optional pre-removal script
        postrm: Optional post-removal script
        conffiles: Optional list of configuration files
        depends: Optional list of package dependencies
        suggests: Optional list of suggested packages
        enhances: Optional list of packages this enhances
        breaks: Optional list of packages this breaks
        conflicts: Optional list of conflicting packages
        replaces: Optional list of packages this replaces
        provides: Optional list of packages this provides
        recommends: Optional list of recommended packages
        **kwargs: Additional arguments passed to pkg_deb
    """

    # Generate version file
    version_name = name + "_version"
    eros_deb_version(
        name = version_name,
        version = version,
        visibility = ["//visibility:private"],
    )

    pkg_deb(
        name = name,
        architecture = _eros_deb_architecture(architecture),
        **_eros_deb_common_args(
            package_name = package_name,
            data = data,
            description = description,
            maintainer = maintainer,
            version_label = ":" + version_name,
            homepage = homepage,
            section = section,
            priority = priority,
            preinst = preinst,
            postinst = postinst,
            prerm = prerm,
            postrm = postrm,
            conffiles = conffiles,
            depends = depends,
            suggests = suggests,
            enhances = enhances,
            breaks = breaks,
            conflicts = conflicts,
            replaces = replaces,
            provides = provides,
            recommends = recommends,
            kwargs = kwargs,
        )
    )

def pkg_eros_deb_multiarch(
        name,
        package_name,
        data,
        description,
        maintainer,
        version = None,
        architectures = ["amd64", "arm64"],
        homepage = "https://example.com",
        section = "libs",
        priority = "optional",
        preinst = None,
        postinst = None,
        prerm = None,
        postrm = None,
        conffiles = None,
        depends = None,
        suggests = None,
        enhances = None,
        breaks = None,
        conflicts = None,
        replaces = None,
        provides = None,
        recommends = None,
        **kwargs):
    """Create explicit per-architecture deb targets for building multiple arches.

    Unlike :func:`pkg_eros_deb` (which emits a single auto-selected target), this
    emits one pkg_deb target per listed architecture (e.g. ``<name>_amd64``,
    ``<name>_arm64``), each tagged ``manual`` so they are excluded from
    ``bazel build //...``. Build the one you want explicitly, e.g.::

        bazel build //:my_deb_arm64 --config=linux_arm64

    A ``<name>`` filegroup groups all per-arch targets for convenient querying.

    Args:
        name: Base name of the rule. Per-arch targets are ``<name>_<arch>``.
        architectures: List of debian architectures to emit (default:
            ["amd64", "arm64"]).
        See :func:`pkg_eros_deb` for the remaining parameters.
    """

    version_name = name + "_version"
    eros_deb_version(
        name = version_name,
        version = version,
        visibility = ["//visibility:private"],
    )

    common = _eros_deb_common_args(
        package_name = package_name,
        data = data,
        description = description,
        maintainer = maintainer,
        version_label = ":" + version_name,
        homepage = homepage,
        section = section,
        priority = priority,
        preinst = preinst,
        postinst = postinst,
        prerm = prerm,
        postrm = postrm,
        conffiles = conffiles,
        depends = depends,
        suggests = suggests,
        enhances = enhances,
        breaks = breaks,
        conflicts = conflicts,
        replaces = replaces,
        provides = provides,
        recommends = recommends,
        kwargs = kwargs,
    )

    per_arch_targets = []
    for arch in architectures:
        target_name = "{}_{}".format(name, arch)
        per_arch_targets.append(target_name)
        pkg_deb(
            name = target_name,
            architecture = arch,
            tags = ["manual"],
            visibility = ["//visibility:private"],
            **common
        )

    # Group all per-arch targets so `bazel build //:<name>` is a meaningful
    # query point (it does not itself build anything; build the _<arch> targets).
    native.filegroup(
        name = name,
        srcs = [":{}".format(t) for t in per_arch_targets],
        visibility = ["//visibility:public"],
    )
