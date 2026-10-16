"""Conan deployer: copy complete packages before CMakeDeps generates metadata."""

import json
import os
from pathlib import Path
import shutil


def capture_sources(source_folder, destination, build_folder=None, generators_folder=None):
    """Keep patched sources/generated headers, not private build/cache products."""
    source = Path(source_folder).resolve()
    build = Path(build_folder).resolve() if build_folder else None
    generators = Path(generators_folder).resolve() if generators_folder else None
    source_suffixes = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inc", ".inl", ".ipp", ".tpp", ".s", ".m", ".mm", ".cu", ".cuh"}
    binary_suffixes = {".o", ".obj", ".lo", ".a", ".la", ".so", ".dll", ".lib", ".dylib", ".exe", ".pdb", ".dwo", ".dwp", ".pyc"}

    def ignored(directory, names):
        directory = Path(directory)
        in_build = build is not None and build != source and directory.resolve().is_relative_to(build)
        omitted = []
        for name in names:
            path = directory / name
            if path.is_symlink() and not path.resolve().is_relative_to(source):
                raise ValueError("debug source symlink escapes locked source tree: " + str(path))
            if path.is_dir():
                if name in {"CMakeFiles", ".git", ".hg", ".svn", "__pycache__"} or (generators and path.resolve() == generators):
                    omitted.append(name)
                continue
            if name in {"CMakeCache.txt", "CMakeUserPresets.json", "cmake_install.cmake", "install_manifest.txt", "build.ninja", ".ninja_deps", ".ninja_log", "conaninfo.txt", "conanmanifest.txt"}:
                omitted.append(name)
            elif name == "Makefile" and (directory / "CMakeCache.txt").exists():
                omitted.append(name)
            elif name.startswith(("conanbuild", "conanrun", "deactivate_conan")):
                omitted.append(name)
            elif path.suffix.lower() in binary_suffixes or ".so." in name:
                omitted.append(name)
            elif in_build and path.suffix.lower() not in source_suffixes:
                omitted.append(name)
            elif path.is_file():
                with path.open("rb") as stream:
                    if stream.read(8).startswith((b"\x7fELF", b"!<arch>\n")):
                        omitted.append(name)
        return omitted

    shutil.copytree(source, destination, symlinks=True, ignore=ignored)
    # A retained source alias must not point at an intentionally excluded build product.
    for path in Path(destination).rglob("*"):
        if path.is_symlink() and not path.exists():
            path.unlink()


def deploy(graph, output_folder, **_kwargs):
    packages = []
    names = set()
    for dep in graph.root.conanfile.dependencies.values():
        if dep.package_folder is None:
            continue
        name = dep.ref.name if dep.context == "host" else "build_" + dep.ref.name
        if name in names:
            raise RuntimeError("ambiguous snapshot package name: " + name)
        names.add(name)
        info = dep.info.dumps()
        if "user.eros:environment=" + os.environ["EROS_ENVIRONMENT_ID"] not in info:
            raise RuntimeError(str(dep.ref) + " removed required Forge environment/flags from package_id")
        for key in ("user.eros:environment", "user.eros:separate_debug", "tools.build:cflags", "tools.build:cxxflags",
                    "tools.build:defines", "tools.build:exelinkflags", "tools.build:sharedlinkflags", "tools.build:compiler_executables"):
            expected = dep.conf.get(key, default=None)
            if expected and dep.info.conf.get(key, default=None) != expected:
                raise RuntimeError(str(dep.ref) + " removed required " + key + " from package_id")
        for key in ("os", "arch", "build_type", "compiler", "compiler.version", "compiler.libcxx", "compiler.cppstd"):
            expected = dep.settings.get_safe(key)
            if expected is not None and str(dep.info.settings.get_safe(key)) != str(expected):
                raise RuntimeError(str(dep.ref) + " removed required " + key + " setting from package_id")
        for key in ("shared", "fPIC"):
            expected = dep.options.get_safe(key)
            if expected is not None and str(dep.info.options.get_safe(key)) != str(expected):
                raise RuntimeError(str(dep.ref) + " removed required " + key + " option from package_id")
        destination = Path(output_folder) / "packages" / name
        shutil.copytree(dep.package_folder, destination, symlinks=True)
        sources = None
        if os.environ.get("EROS_CAPTURE_SOURCES") == "1":
            source_folder = dep.folders.source_folder
            if source_folder and Path(source_folder).is_dir():
                sources = "sources/" + name
                capture_sources(source_folder, Path(output_folder) / sources,
                                dep.folders.build_folder, dep.folders.generators_folder)
        # Keep info available to validate a precompiled binary's actual package identity.
        packages.append({"name": name, "reference": str(dep.ref), "context": dep.context,
                         "package_info": info,
                         "source_snapshot": sources,
                         "original_package_folder": str(dep.package_folder)})
        dep.set_deploy_folder(str(destination))
    (Path(output_folder) / "deployed.json").write_text(json.dumps(packages, indent=2))
