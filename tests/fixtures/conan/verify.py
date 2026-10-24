"""Controlled Conan acceptance tests. No user cache and no conancenter access."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "bazel" / "tools"
sys.path.insert(0, str(TOOLS))
from action_common import conan_command, has_debug, inventory, load_environment, sha256, write_json


class Checks:
    def __init__(self, args):
        self.args = args
        self.evidence = Path(args.evidence).resolve()
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        startup = args.bazel_startup or ["--bazelrc=bazel/bazelrc", f"--output_base={self.evidence / 'bazel-output-base'}"]
        bases = [option.split("=", 1)[1] for option in startup if option.startswith("--output_base=")]
        if len(bases) != 1 or not Path(bases[0]).is_absolute():
            raise ValueError("Bazel startup options must contain exactly one absolute --output_base")
        self.output_base = Path(bases[0]).resolve()
        self.bazel = ["bazel", *startup]
        actual_base = Path(self.command(self.bazel + ["info", "output_base"]).stdout.strip()).resolve()
        if actual_base != self.output_base:
            raise AssertionError(f"Bazel output_base mismatch: expected {self.output_base}, got {actual_base}")
        execution_root = Path(self.command(self.bazel + ["info", "execution_root"]).stdout.strip())
        query = self.command(self.bazel + ["cquery", "@eros_host_tools//:env_manifest", "--output=files"])
        paths = [(execution_root.parent.parent if line.startswith("external/") else execution_root) / line
                 for line in query.stdout.splitlines() if line.endswith("env_manifest.json")]
        if len(paths) != 1:
            raise AssertionError("could not locate exactly one controlled environment manifest")
        self.environment = self.evidence / "environment.json"
        shutil.copy2(paths[0].resolve(), self.environment)
        self.manifest = json.loads(self.environment.read_text())
        self.conan = conan_command(self.manifest)
        self.profiles = ROOT / "bazel" / "toolchain" / "conan"

    def command(self, command, env=None, cwd=ROOT, succeeds=True):
        self.sequence += 1
        result = subprocess.run([str(c) for c in command], cwd=cwd, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
        prefix = self.evidence / ("%03d" % self.sequence)
        prefix.with_suffix(".command.json").write_text(json.dumps([str(c) for c in command], indent=2))
        prefix.with_suffix(".stdout").write_text(result.stdout)
        prefix.with_suffix(".stderr").write_text(result.stderr)
        prefix.with_suffix(".exit").write_text(str(result.returncode) + "\n")
        if succeeds and result.returncode:
            raise AssertionError("command failed, evidence " + str(prefix) + ":\n" + result.stderr[-5000:] + result.stdout[-1000:])
        if not succeeds and not result.returncode:
            raise AssertionError("negative command unexpectedly succeeded: " + str(prefix))
        return result

    def environment_for(self, work, name):
        _, env = load_environment(self.environment, work / (name + "_home"))
        env["CONAN_HOME"] = str(work / (name + "_conan"))
        self.command(self.conan + ["remote", "list"], env)
        self.command(self.conan + ["remote", "remove", "*"], env)
        return env

    def profile(self, work, suffix="release", debug=False, extra="", preset=None):
        profile = work / ("host_" + suffix + "_" + str(debug) + "_" + str(self.sequence) + ".profile")
        base = self.profiles / ((preset or self.args.preset) + "_" + suffix + ".profile")
        profile.write_text("include(" + str(base) + ")\n[conf]\n"
                           "user.eros:environment=" + self.manifest["environment_sha256"] + "\n"
                           "user.eros:separate_debug=" + str(debug) + "\n"
                           'tools.info.package_id:confs=["user\\.eros:.*", "tools\\.build:(?!jobs$).*"]\n' + extra)
        return profile

    @contextmanager
    def server(self, work):
        packages = Path(self.args.server_pythonpath)
        if not (packages / "conans" / "server").is_dir():
            if not self.args.bootstrap_server:
                raise RuntimeError("BLOCKED: isolated conan-server unavailable; use --bootstrap-server or --server-pythonpath")
            self.command([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--target", str(packages), "conan-server==2.33.0"])
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server_home = work / "server"
        server_home.mkdir()
        (server_home / "server.conf").write_text(
            "[server]\njwt_secret=forge-local-test-only-secret-32-bytes\njwt_expire_minutes=120\n"
            "ssl_enabled=False\nport=" + str(port) + "\npublic_port=" + str(port) + "\n"
            "host_name=127.0.0.1\nauthorize_timeout=1800\ndisk_storage_path=./data\n"
            "disk_authorize_timeout=1800\nupdown_secret=forge-local-test-only-secret-32-bytes\n"
            "[write_permissions]\n*/*@*/*: forge\n[read_permissions]\n*/*@*/*: *\n"
            "[users]\nforge=fixture-password\n")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(work / "server_user_home"),
               "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(packages),
               "CONAN_SERVER_HOME": str(server_home)}
        log = (self.evidence / "conan_server.log").open("w")
        # Bind only loopback, unlike conan_server's default launcher.
        process = subprocess.Popen([sys.executable, "-s", "-c",
                                    "from conans.server.launcher import ServerLauncher; "
                                    "import os; ServerLauncher(server_dir=os.environ['CONAN_SERVER_HOME']).server.run(host='127.0.0.1')"],
                                   env=env, cwd=work, stdout=log, stderr=subprocess.STDOUT)
        url = "http://127.0.0.1:" + str(port)
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise AssertionError("isolated conan_server exited; see " + str(log.name))
                try:
                    with urllib.request.urlopen(url + "/v2/ping", timeout=1):
                        break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise AssertionError("isolated conan_server not ready")
                    time.sleep(0.05)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()

    def seed(self, work, url, stripped=False):
        env = self.environment_for(work, "producer")
        self.command(self.conan + ["remote", "add", "fixture", url], env)
        self.command(self.conan + ["remote", "login", "fixture", "forge", "-p", "fixture-password"], env)
        index = work / "recipes"
        shutil.copytree(Path(__file__).parent / "remote", index)
        for name in ("leaf", "bar"):
            self.command(self.conan + ["export", str(index / "recipes" / name / "all"), "--version=1.0"], env)
        host = self.profile(work, extra="tools.build:install_strip=True\n" if stripped else "")
        output = work / "producer_output"
        result = self.command(self.conan + ["install", str(Path(__file__).parent / "conanfile.txt"),
                              "--lockfile=" + str(Path(__file__).parent / "conan.lock"), "--build=missing",
                              "--profile:host=" + str(host), "--profile:build=" + str(self.profiles / (self.args.preset + "_build_release.profile")),
                              "--format=json", "--output-folder=" + str(output)], env)
        graph = json.loads(result.stdout)["graph"]["nodes"].values()
        nodes = [n for n in graph if n.get("package_id") and n.get("ref")]
        pins = []
        for node in nodes:
            folder = Path(node["package_folder"])
            library = folder / "lib" / ("lib" + node["name"] + ".a")
            if stripped:
                assert not has_debug(library, self.manifest["tools"], env), "seed did not really strip its debug sections"
            pins.append({"name": node["name"], "ref": node["ref"], "package_id": node["package_id"],
                         "prev": node["prev"], "remote": "fixture",
                         "files": {f["path"]: f["sha256"] for f in inventory(folder) if "sha256" in f}})
        self.command(self.conan + ["upload", "*", "--remote=fixture", "--confirm"], env)
        return env, index, pins

    def snapshot(self, work, name="snapshot", remote=None, suffix="release", debug=False,
                 lock=None, conanfile=None, preset=None, host=None):
        directory = work / name
        directory.mkdir()
        config = {"output": str(directory / "install"), "manifest": str(directory / "manifest.json"),
                  "debug_output": str(directory / "debug"), "debug_manifest": str(directory / "debug_manifest.json"),
                  "environment": str(self.environment), "preset": preset or self.args.preset,
                  "conanfile": str(conanfile or Path(__file__).parent / "conanfile.txt"),
                  "lockfile": str(lock or Path(__file__).parent / "conan.lock"),
                  "host_profile": str(host or self.profiles / ((preset or self.args.preset) + "_" + suffix + ".profile")),
                  "build_profile": str(self.profiles / (self.args.preset + "_build_release.profile")),
                  "deployer": str(TOOLS / "snapshot_deployer.py"), "jobs": 1,
                  "separate_debug": debug, "sanitizer": suffix if suffix in ("asan", "ubsan", "tsan", "asan_ubsan") else "none"}
        if remote:
            remote_path = directory / "binary_lock.json"
            write_json(remote_path, remote)
            config["remote_config"] = str(remote_path)
        else:
            config["file_remote"] = str(Path(__file__).parent / "remote")
        config_path = directory / "config.json"
        write_json(config_path, config)
        self.command([sys.executable, "-s", str(TOOLS / "conan_action.py"), "--config", str(config_path)], cwd=directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        write_json(self.evidence / (name + "_manifest.json"), manifest)
        assert manifest["private_home_removed"]
        assert not list(directory.glob("forge-conan-*")), "temporary home not removed"
        return directory / "install", manifest

    def consumer(self, work, snapshot, expected=43):
        source = work / ("consumer_" + str(self.sequence) + ".cc")
        source.write_text('#include "forge_dependency.h"\n#include <iostream>\nint main(){int n=forge_dependency_value(20);std::cout<<n<<"\\n";return n==' + str(expected) + '?0:1;}\n')
        binary = source.with_suffix("")
        _, env = load_environment(self.environment, work / "consumer_home")
        self.command([self.manifest["tools"]["g++"]["path"], str(source),
                      "-I" + str(snapshot / "packages/bar/include"),
                      str(snapshot / "packages/bar/lib/libbar.a"), str(snapshot / "packages/leaf/lib/libleaf.a"),
                      "-pthread", "-o", str(binary)], env)
        self.command([str(binary)], env)

    def remote_case(self, work):
        with self.server(work) as url:
            env, index, pins = self.seed(work, url, stripped=self.args.tc == "TC-DBG-02")
            remote = {"remotes": {"fixture": url}, "packages": pins}
            if self.args.tc in ("TC-DEP-01", "TC-DEP-02"):
                old_lock = (Path(__file__).parent / "conan.lock").read_bytes()
                bar = index / "recipes/bar/all/conanfile.py"
                bar.write_text(bar.read_text() + "\n# controlled new recipe revision\n")
                self.command(self.conan + ["export", str(bar), "--version=1.0"], env)
                self.command(self.conan + ["export", str(bar), "--version=2.0"], env)
                self.command(self.conan + ["upload", "bar/*", "--remote=fixture", "--confirm"], env)
                listed = self.command(self.conan + ["list", "bar/*#*", "--remote=fixture", "--format=json"], env)
                assert "bar/2.0" in listed.stdout
                if self.args.tc == "TC-DEP-02":
                    package = work / "updated_package"
                    package.mkdir()
                    shutil.copy2(Path(__file__).parent / "conanfile.txt", package / "conanfile.txt")
                    (package / "conan.lock").write_bytes(old_lock)
                    other = work / "other_package.lock"
                    other.write_bytes(old_lock)
                    self.command(self.bazel + ["run", "--config=" + self.args.preset, "//bazel/tools:conan_lock_update", "--",
                                              str(package), "--remote", "fixture=" + url])
                    updated = json.loads((package / "conan.lock").read_text())
                    assert any(ref.startswith("bar/2.0#") for ref in updated["requires"])
                    assert other.read_bytes() == old_lock
                    remote["packages"] = [p for p in pins if p["name"] == "leaf"]
                    snapshot, result = self.snapshot(work, remote=remote, lock=package / "conan.lock", conanfile=package / "conanfile.txt")
                    assert any(p["ref"].startswith("bar/2.0#") for p in result["packages"])
                else:
                    snapshot, result = self.snapshot(work, remote=remote)
                    assert all(p["ref"].startswith(p["name"] + "/1.0#") for p in pins)
                    assert all(p["ref"] in {q["ref"] for q in pins} for p in result["packages"])
                assert (Path(__file__).parent / "conan.lock").read_bytes() == old_lock
                self.consumer(work, snapshot)
            elif self.args.tc == "TC-DEP-03":
                snapshot, result = self.snapshot(work, remote=remote)
                assert result["pinned_binary_downloads"]
                assert all(p["binary"] == "Cache" for p in result["packages"])
                self.consumer(work, snapshot)
            elif self.args.tc == "TC-DBG-02":
                # The only uploaded packages are actually stripped, ordinary Release.
                # Required-symbol identity selects a different binary and builds it.
                snapshot, result = self.snapshot(work, remote={"remotes": {"fixture": url}, "packages": []}, debug=True)
                assert all(p["binary"] == "Build" for p in result["packages"])
                assert all(p["package_id"] != q["package_id"] for p in result["packages"] for q in pins if p["ref"] == q["ref"])
                assert has_debug(snapshot / "packages/bar/lib/libbar.a", self.manifest["tools"], env)
                self.consumer(work, snapshot)

    def run(self):
        with tempfile.TemporaryDirectory(prefix="work-", dir=self.evidence) as temporary:
            work = Path(temporary)
            tc = self.args.tc
            if tc in ("TC-DEP-01", "TC-DEP-02", "TC-DEP-03", "TC-DBG-02"):
                self.remote_case(work)
            elif tc == "TC-DEP-04":
                snapshot, result = self.snapshot(work)
                assert {p["binary"] for p in result["packages"]} == {"Build"}
                self.consumer(work, snapshot)
            elif tc == "TC-DEP-05":
                for target, expected in (("missing_lock_entry", "lockfile"), ("bad_digest", "controlled source checksum mismatch"),
                                         ("broken_recipe", "controlled locked recipe compilation failure")):
                    result = self.command(self.bazel + ["build", "--config=" + self.args.preset, "//tests/fixtures/fail:" + target], succeeds=False)
                    assert expected.lower() in (result.stdout + result.stderr).lower()
            elif tc == "TC-DEP-06":
                identities = []
                for suffix, debug in (("release", False), ("debug", False), ("asan", False), ("asan_ubsan", False), ("release", True)):
                    _, result = self.snapshot(work, name=suffix + str(debug), suffix=suffix, debug=debug)
                    identities.append(next(p["package_id"] for p in result["packages"] if p["ref"].startswith("bar/")))
                host = self.profile(work, extra="\n[options]\n*:fPIC=False\n")
                _, result = self.snapshot(work, name="nonpic", host=host)
                identities.append(next(p["package_id"] for p in result["packages"] if p["ref"].startswith("bar/")))
                _, result = self.snapshot(work, name="cross", preset=self.args.preset + "_cross_arm64")
                identities.append(next(p["package_id"] for p in result["packages"] if p["ref"].startswith("bar/")))
                assert len(set(identities)) == len(identities), "variant identities unexpectedly alias"
                write_json(self.evidence / "package_ids.json", identities)
            elif tc == "TC-DEP-07":
                # Work on an independent package/recipe copy; source checkout stays unchanged.
                index = work / "index"
                shutil.copytree(Path(__file__).parent / "remote", index)
                env = self.environment_for(work, "mutation")
                self.command(self.conan + ["remote", "add", "files", str(index), "-t", "local-recipes-index"], env)
                patch = index / "recipes/bar/all/patches/value.patch"
                patch.write_text(patch.read_text().replace("forge_bar_patch_value = 2", "forge_bar_patch_value = 3"))
                package = work / "package"
                package.mkdir()
                shutil.copy2(Path(__file__).parent / "conanfile.txt", package / "conanfile.txt")
                self.command([sys.executable, str(TOOLS / "conan_lock_update.py"), str(package), "--environment", str(self.environment),
                              "--file-remote", str(index)])
                changed = json.loads((package / "conan.lock").read_text())
                original = json.loads((Path(__file__).parent / "conan.lock").read_text())
                assert {r.split("%", 1)[0] for r in changed["requires"]} != {r.split("%", 1)[0] for r in original["requires"]}
                # A real install consumes the changed patch and exact updated revision.
                host = self.profile(work)
                result = self.command(self.conan + ["install", str(package / "conanfile.txt"), "--lockfile=" + str(package / "conan.lock"),
                                      "--profile:host=" + str(host), "--profile:build=" + str(self.profiles / (self.args.preset + "_build_release.profile")),
                                      "--build=missing", "--format=json", "--output-folder=" + str(work / "mutated_generators"),
                                      "--deployer=" + str(TOOLS / "snapshot_deployer.py"), "--deployer-folder=" + str(work / "mutated_snapshot")],
                                      dict(env, EROS_ENVIRONMENT_ID=self.manifest["environment_sha256"]))
                assert all(n["binary"] == "Build" for n in json.loads(result.stdout)["graph"]["nodes"].values() if n.get("package_id"))
                self.consumer(work, work / "mutated_snapshot", expected=44)
            elif tc == "TC-CACHE-04":
                snapshot, _ = self.snapshot(work)
                relocated = work / "different_absolute_root" / "snapshot"
                shutil.copytree(snapshot, relocated)
                shutil.rmtree(snapshot)
                for metadata in (relocated / "generators").glob("*.cmake"):
                    text = metadata.read_text()
                    assert "conan_home" not in text and str(snapshot) not in text
                source = work / "consumer_source"
                shutil.copytree(ROOT / "tests/fixtures/link", source)
                configuration = {
                    "output": str(work / "cmake_install"), "manifest": str(work / "cmake_manifest.json"),
                    "debug_output": str(work / "cmake_debug"), "debug_manifest": str(work / "cmake_debug_manifest.json"),
                    "environment": str(self.environment), "preset": self.args.preset, "source_root": str(source),
                    "sources": [str(source / p) for p in ("CMakeLists.txt", "foo.cc", "foo.h", "public_config.h.in", "settings.cmake")],
                    "toolchain": str(ROOT / "bazel/toolchain/cmake" / (self.args.preset + ".cmake")),
                    "conan_snapshot": str(relocated), "target": "", "cache_entries": {},
                    "declared": {"lib/libfoo.a": str(work / "libfoo.a"), "include/public_config.h": str(work / "public_config.h")},
                    "build_type": "Release", "sanitizer": "none", "separate_debug": False,
                    "static_cpp_runtime": False, "jobs": 1,
                }
                config = work / "cmake_config.json"
                write_json(config, configuration)
                self.command([sys.executable, str(TOOLS / "cmake_action.py"), "--config", str(config)], cwd=work)
                self.consumer(work, relocated)
            else:
                raise AssertionError("unimplemented Conan verification case: " + tc)
        write_json(self.evidence / "result.json", {"tc": self.args.tc, "status": "PASS", "commands": self.sequence})
        print(self.args.tc + " PASS; evidence=" + str(self.evidence))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tc", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--preset", default="linux_arm64")
    parser.add_argument("--bazel-startup", action="append", default=[], metavar="OPTION",
                        help="Bazel startup option (use --bazel-startup=--option=value; repeat for the runner's startup options)")
    parser.add_argument("--server-pythonpath", default="/tmp/kilo/forge-conan-server")
    parser.add_argument("--bootstrap-server", action="store_true")
    args = parser.parse_args()
    try:
        Checks(args).run()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(77 if str(error).startswith("BLOCKED:") else 1) from error
