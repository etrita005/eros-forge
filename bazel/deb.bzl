# Copyright (c) 2024 EROS Project
# deb.bzl - EROS Debian package build rules
#
# This module provides a simplified way to build deb packages for EROS projects
# with automatic architecture detection based on Bazel config.
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
#       version = "1.0.0",  # Optional, defaults to DEB_VERSION env or "0.1.0"
#   )
#
# Then build with:
#   bazel build --config=arm64 //:my_package_deb   # Builds arm64 deb
#   bazel build --config=x86_64 //:my_package_deb  # Builds x86_64 deb

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
    """Generate version file for deb package."""
    output = ctx.actions.declare_file(ctx.attr.name + ".txt")

    # Priority: 1. Explicit version attr, 2. --define=DEB_VERSION=xxx, 3. Default "0.1.0"
    if ctx.attr.version:
        version = ctx.attr.version
    else:
        # Try to get from --define=DEB_VERSION=xxx
        define_version = ctx.var.get("DEB_VERSION", "")
        if define_version:
            version = define_version
        else:
            version = "0.1.0"

    ctx.actions.write(
        output = output,
        content = version,
    )

    return [DefaultInfo(files = depset([output]))]

eros_deb_version = rule(
    implementation = _eros_deb_version_impl,
    attrs = {
        "version": attr.string(
            doc = "Default version string. Can be overridden by --define=DEB_VERSION=xxx.",
        ),
    },
    doc = "Generates a version file for deb package, respecting --define=DEB_VERSION=xxx.",
)

def pkg_eros_deb(
        name,
        package_name,
        data,
        description,
        maintainer,
        version = None,
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

    This macro creates the necessary rules to build a deb package that automatically
    detects the target architecture based on Bazel's platform configuration.

    Args:
        name: Name of the rule
        package_name: Name of the debian package (e.g., "my-package")
        data: Label of the pkg_tar target containing the package data
        description: Package description
        maintainer: Package maintainer (e.g., "Team <team@example.com>")
        version: Default version string. Can be overridden by DEB_VERSION env var
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

    # Create architecture-specific deb packages using select()
    # We use a genrule to select the appropriate deb based on platform

    # Define architecture-specific deb packages
    pkg_deb(
        name = name + "_amd64",
        package = package_name,
        architecture = "amd64",
        data = data,
        description = description,
        maintainer = maintainer,
        homepage = homepage,
        section = section,
        priority = priority,
        version_file = ":" + version_name,
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
        tags = ["manual"],
        visibility = ["//visibility:private"],
        **kwargs
    )

    pkg_deb(
        name = name + "_arm64",
        package = package_name,
        architecture = "arm64",
        data = data,
        description = description,
        maintainer = maintainer,
        homepage = homepage,
        section = section,
        priority = priority,
        version_file = ":" + version_name,
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
        tags = ["manual"],
        visibility = ["//visibility:private"],
        **kwargs
    )

    # Use alias with select to choose the right architecture
    native.alias(
        name = name,
        actual = select({
            "@platforms//cpu:x86_64": name + "_amd64",
            "@platforms//cpu:arm64": name + "_arm64",
            "//conditions:default": name + "_amd64",
        }),
        visibility = ["//visibility:public"],
    )
