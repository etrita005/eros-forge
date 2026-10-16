"""Explicit sandbox-external package lock maintenance, using an isolated home."""

import argparse
import os
from pathlib import Path
import tempfile
import shutil

from action_common import conan_command, load_environment, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_directory")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--file-remote", action="append", default=[])
    parser.add_argument("--remote", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--host-profile")
    parser.add_argument("--build-profile")
    parser.add_argument("--lockfile", default="conan.lock")
    args = parser.parse_args()
    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", Path.cwd()))
    package = (workspace / args.package_directory).resolve()
    conanfile = next((package / name for name in ("conanfile.py", "conanfile.txt")
                      if (package / name).is_file()), None)
    if conanfile is None:
        parser.error("package directory has no conanfile.py or conanfile.txt")
    with tempfile.TemporaryDirectory(prefix="forge-lock-update-") as temporary:
        manifest, env = load_environment(args.environment, Path(temporary) / "home")
        env["CONAN_HOME"] = str(Path(temporary) / "conan")
        conan = conan_command(manifest)
        run(conan + ["remote", "list"], env)
        run(conan + ["remote", "remove", "*"], env)
        for index, path in enumerate(args.file_remote):
            local_index = Path(temporary) / ("remote" + str(index))
            shutil.copytree((workspace / path).resolve(), local_index, symlinks=False)
            run(conan + ["remote", "add", "files" + str(index), str(local_index),
                         "-t", "local-recipes-index"], env)
        for remote in args.remote:
            name, url = remote.split("=", 1)
            run(conan + ["remote", "add", name, url], env)
        cpu = "arm64" if manifest["host"]["cpu"] in ("aarch64", "arm64") else "x86_64"
        profiles = workspace / "bazel" / "toolchain" / "conan"
        host = workspace / args.host_profile if args.host_profile else profiles / ("linux_" + cpu + "_release.profile")
        build = workspace / args.build_profile if args.build_profile else profiles / ("linux_" + cpu + "_build_release.profile")
        destination = (package / args.lockfile).resolve()
        if not destination.is_relative_to(package):
            parser.error("lock output must stay inside the requested package directory")
        run(conan + ["lock", "create", str(conanfile), "--lockfile=", "--update",
                     "--profile:host=" + str(host.resolve()), "--profile:build=" + str(build.resolve()),
                     "--lockfile-out=" + str(destination)], env)
        print("Explicitly updated lock: " + str(destination))


if __name__ == "__main__":
    main()
