"""Thin host-side Docker transport for Forge Bazel and interactive shells."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "docker/image.lock.json"
TAG = "eros-forge-builder:local"
PASSTHROUGH = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy", "DEB_VERSION")
STARTUP_PATHS = ("--bazelrc", "--output_base", "--output_user_root")


def docker(*args):
    try:
        result = subprocess.run(["docker", *args], text=True, capture_output=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("Docker is required to use the Forge build environment") from None
    if result.returncode:
        raise RuntimeError("docker " + args[0] + " failed: " + (result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()


def workspace_root():
    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / "MODULE.bazel").is_file():
            return directory.resolve()
    raise RuntimeError("Run Forge from a Bazel module (directory containing MODULE.bazel)")


def metadata_mounts(root):
    result = []
    dotgit = root / ".git"
    if dotgit.is_file() and not dotgit.is_symlink():
        line = dotgit.read_text().strip()
        if not line.startswith("gitdir: "):
            raise RuntimeError("Unrecognized Git metadata link: " + str(dotgit))
        gitdir = (root / line[8:]).resolve()
    elif dotgit.is_symlink():
        gitdir = dotgit.resolve()
    elif dotgit.is_dir():
        gitdir = dotgit.resolve()
    else:
        return result
    if not gitdir.is_dir():
        raise RuntimeError("Git metadata is unavailable: " + str(gitdir))
    if not gitdir.is_relative_to(root):
        result.append(gitdir)
    commondir_file = gitdir / "commondir"
    common = (gitdir / commondir_file.read_text().strip()).resolve() if commondir_file.is_file() else gitdir
    if not common.is_dir():
        raise RuntimeError("Git common metadata is unavailable: " + str(common))
    if not common.is_relative_to(root):
        result.append(common)
    objects = (common / "objects").resolve()
    if objects.is_dir() and not objects.is_relative_to(common):
        result.append(objects)
    alternates = objects / "info/alternates"
    if alternates.is_file():
        for line in alternates.read_text().splitlines():
            path = (objects / line).resolve()
            if not path.is_dir():
                raise RuntimeError("Git object alternate is missing: " + str(path))
            result.append(path)
    return [path for path in result if not any(path != other and path.is_relative_to(other) for other in result)]


def mounted_path(path, roots):
    return any(path.is_relative_to(root) for root in roots) or path == Path("/dev/null")


def check_startup_paths(arguments, roots, state):
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        argument = arguments[index]
        consumed = 1
        for option in STARTUP_PATHS:
            if argument == option:
                if index + 1 == len(arguments):
                    raise RuntimeError(option + " requires a path")
                value = arguments[index + 1]
                consumed = 2
            elif argument.startswith(option + "="):
                value = argument[len(option) + 1:]
            else:
                continue
            path = (Path.cwd() / value).resolve()
            if not mounted_path(path, roots):
                raise RuntimeError(option + " must point into a mounted workspace: " + value)
            if option != "--bazelrc" and not path.is_relative_to(state):
                raise RuntimeError(option + " must stay inside the current instance state: " + value)
        index += consumed
    return arguments[:index]


def mount(source, destination=None, readonly=False):
    destination = destination or source
    if "," in str(source) or "," in str(destination):
        raise RuntimeError("Docker bind mount paths containing commas are unsupported: " + str(source))
    return "type=bind,src=" + str(source) + ",dst=" + str(destination) + (",readonly" if readonly else "")


def main(mode, arguments):
    try:
        if mode == "shell" and arguments:
            raise RuntimeError("forge-shell takes no arguments; use bazel inside the shell")
        workspace = workspace_root()
        lock = json.loads(LOCK.read_text())
        if lock["schema_version"] != 1 or lock["platform"] != "linux/amd64":
            raise RuntimeError("Unsupported local Forge image baseline")
        image, platform = docker("image", "inspect", TAG, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}").split()
        if (image, platform) != (lock["image"], lock["platform"]):
            raise RuntimeError("Local Forge image differs from docker/image.lock.json; rebuild and review it explicitly")
        image_environment = dict(item.split("=", 1) for item in json.loads(
            docker("image", "inspect", TAG, "--format", "{{json .Config.Env}}")))
        uid, gid = os.getuid(), os.getgid()
        instance = os.environ.get("FORGE_INSTANCE", "default")
        if not instance or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in instance):
            raise RuntimeError("FORGE_INSTANCE must contain only letters, digits, '_' or '-'")
        key = hashlib.sha256(json.dumps([str(workspace), image, uid, gid, instance]).encode()).hexdigest()[:20]
        name = "eros-forge-" + key
        state = Path.home() / ".cache/eros-forge" / key
        if state.resolve().is_relative_to(Path("/tmp/kilo")):
            raise RuntimeError("HOME must not be inside /tmp/kilo, which is bind-mounted for container temporary files")
        if any(state.resolve().is_relative_to(root) for root in (ROOT, workspace)):
            raise RuntimeError("Forge state must be outside source workspaces; choose a HOME outside the checkout")
        source_roots = {ROOT, workspace}
        metadata = set(metadata_mounts(ROOT)) | set(metadata_mounts(workspace))
        roots = source_roots | metadata | {state}
        startup = check_startup_paths(arguments, roots, state) if mode == "bazel" else []
        state.mkdir(parents=True, exist_ok=True)
        (state / "home").mkdir(exist_ok=True)
        (state / "tmp").mkdir(exist_ok=True)
        bindings = [(path, path, False) for path in sorted(source_roots)
                    if not any(path != other and path.is_relative_to(other) for other in source_roots)]
        bindings += [(path, path, True) for path in sorted(metadata)
                     if not any(path.is_relative_to(root) for root in source_roots)]
        bindings += [(state, state, False), (state / "tmp", Path("/tmp/kilo"), False)]
        mounts = []
        for source, destination, readonly in bindings:
            mounts += ["--mount", mount(source, destination, readonly)]
        workspace_locks = Path.home() / ".cache/eros-forge/workspace-locks"
        workspace_locks.mkdir(parents=True, exist_ok=True)
        workspace_key = hashlib.sha256(json.dumps([str(workspace), uid, gid]).encode()).hexdigest()
        with (workspace_locks / workspace_key).open("a+") as workspace_lock, \
             (state / "startup.lock").open("a+") as lockfile:
            fcntl.flock(workspace_lock, fcntl.LOCK_EX)
            fcntl.flock(lockfile, fcntl.LOCK_EX)
            running = docker("ps", "--filter", "label=eros.forge.workspace=" + str(workspace),
                             "--format", "{{.Names}}").splitlines()
            if any(other != name for other in running):
                raise RuntimeError("Another Forge instance is running for this workspace; use a separate checkout")
            try:
                container = json.loads(docker("container", "inspect", name))[0]
            except RuntimeError as error:
                if "No such object" not in str(error) and "No such container" not in str(error):
                    raise
                docker("run", "-d", "--init", "--name", name, "--network=host", "--user", f"{uid}:{gid}",
                       "--cap-drop=ALL", "--security-opt=no-new-privileges", "--label", "eros.forge.image=" + image,
                       "--label", "eros.forge.workspace=" + str(workspace),
                       "--label", "eros.forge.instance=" + instance, "--workdir", str(workspace),
                       "--env", "HOME=" + str(state / "home"), "--env", "PYTHONDONTWRITEBYTECODE=1",
                       *mounts, image, "sleep", "infinity")
                container = json.loads(docker("container", "inspect", name))[0]
            if container["Image"] != image or container["Config"]["User"] != f"{uid}:{gid}":
                raise RuntimeError("Existing Forge container has a different image or user; stop it explicitly")
            labels = container["Config"].get("Labels") or {}
            if labels.get("eros.forge.workspace") != str(workspace) or labels.get("eros.forge.instance") != instance:
                raise RuntimeError("Existing Forge container belongs to another workspace or instance")
            environment = dict(value.split("=", 1) for value in container["Config"]["Env"])
            expected_environment = dict(image_environment, HOME=str(state / "home"), PYTHONDONTWRITEBYTECODE="1")
            if environment != expected_environment:
                raise RuntimeError("Existing Forge container has a different environment; stop it explicitly")
            actual_mounts = {item["Destination"]: (item["Source"], item["RW"])
                             for item in container["Mounts"] if item["Type"] == "bind"}
            expected_mounts = {str(destination): (str(source), not readonly)
                               for source, destination, readonly in bindings}
            host = container["HostConfig"]
            if (actual_mounts != expected_mounts or host["NetworkMode"] != "host" or host["Privileged"]
                    or host["CapAdd"]
                    or "all" not in [cap.lower() for cap in host["CapDrop"] or []]
                    or "no-new-privileges" not in host["SecurityOpt"] or []):
                raise RuntimeError("Existing Forge container has unexpected mounts or security settings; stop it explicitly")
            if not container["State"]["Running"]:
                docker("start", name)
        docker("exec", "--workdir", "/tmp", name, "/usr/bin/python3", str(ROOT / "docker/verify_environment.py"))
        output_base = docker("exec", "--workdir", str(Path.cwd().resolve()),
                             "--env", "HOME=" + str(state / "home"), name,
                             "/usr/local/bin/bazel", *startup, "info", "output_base")
        if not Path(output_base).resolve().is_relative_to(state):
            raise RuntimeError("Effective Bazel output base escapes this instance: " + output_base)
        argv = ["docker", "exec", "--interactive", "--workdir", str(Path.cwd().resolve())]
        if sys.stdin.isatty() and sys.stdout.isatty():
            argv.append("--tty")
        argv += ["--env", "HOME=" + str(state / "home"),
                 "--env", "EROS_FORGE_IMAGE_ID=" + image,
                 "--env", "EROS_FORGE_ENVIRONMENT_SHA256=" + lock["environment_sha256"]]
        for variable in PASSTHROUGH:
            if variable in os.environ:
                argv += ["--env", variable + "=" + os.environ[variable]]
        signal_file = state / "tmp" / ("exec-" + uuid.uuid4().hex + ".pid")
        command = (["/usr/local/bin/bazel", *arguments] if mode == "bazel"
                   else ["/bin/bash", "--noprofile", "--norc"])
        argv += [name, "/usr/bin/python3", str(ROOT / "docker/exec_command.py"), str(signal_file), *command]
        pending = []

        def forward(signum, _frame):
            pending.append(signum)
            if not signal_file.is_file():
                return
            pid = signal_file.read_text().strip()
            while pending:
                current = pending.pop(0)
                subprocess.run(["docker", "exec", name, "/bin/kill", "-s", signal.Signals(current).name, pid],
                               capture_output=True, check=False, timeout=10)

        handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
        try:
            for signum in handlers:
                signal.signal(signum, forward)
            process = subprocess.Popen(argv)
            deadline = time.monotonic() + 10
            while not signal_file.is_file() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if pending:
                forward(pending.pop(0), None)
            return process.wait()
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
            signal_file.unlink(missing_ok=True)
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        print("forge-" + mode + ": " + str(error), file=sys.stderr)
        raise SystemExit(1) from None
