"""Host entry contract tests; Docker integration is explicit opt-in."""

from contextlib import redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import forge_container


def temporary_workspace():
    directory = tempfile.TemporaryDirectory(prefix="forge-entry-", dir=ROOT.parent)
    workspace = Path(directory.name)
    (workspace / "MODULE.bazel").write_text('module(name = "forge_entry_test")\n')
    return directory, workspace


class ContainerEntryTests(unittest.TestCase):
    def test_startup_paths_respect_declared_mounts(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            (root / "project.bazelrc").write_text("")
            state = root / "state"
            with patch.object(forge_container.Path, "cwd", return_value=root):
                forge_container.check_startup_paths(
                    ["--bazelrc=project.bazelrc", "--output_base=" + str(state / "out"), "build", "//..."],
                    {root, state}, state,
                )
                with self.assertRaisesRegex(RuntimeError, "must point into a mounted workspace"):
                    forge_container.check_startup_paths(["--output_base=/unmounted/base", "query", "//..."],
                                                        {root, state}, state)
                with self.assertRaisesRegex(RuntimeError, "current instance state"):
                    forge_container.check_startup_paths(["--output_base=" + str(root / "shared"), "query", "//..."],
                                                        {root, state}, state)

    def test_repo_metadata_includes_external_git_objects(self):
        git = ROOT / ".git"
        if not git.is_symlink():
            self.skipTest("This checkout has self-contained Git metadata")
        mounts = forge_container.metadata_mounts(ROOT)
        self.assertIn(git.resolve(), mounts)
        self.assertIn((git.resolve() / "objects").resolve(), mounts)

    def test_linked_worktree_mounts_shared_git_directory(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            worktree = root / "worktree"
            gitdir = root / "common/.git/worktrees/example"
            gitdir.mkdir(parents=True)
            (root / "common/.git/objects").mkdir()
            worktree.mkdir()
            (worktree / ".git").write_text("gitdir: ../common/.git/worktrees/example\n")
            (gitdir / "commondir").write_text("../..\n")
            self.assertEqual(forge_container.metadata_mounts(worktree), [root / "common/.git"])

    def test_wrong_image_refuses_fallback(self):
        with patch.object(forge_container, "workspace_root", return_value=ROOT), \
             patch.object(forge_container, "docker", return_value="sha256:wrong linux/amd64"), \
             redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as exit_status:
                forge_container.main("bazel", ["query", "//..."])
        self.assertEqual(exit_status.exception.code, 1)
        self.assertIn("differs from docker/image.lock.json", stderr.getvalue())

    def test_existing_container_with_wrong_mounts_is_rejected(self):
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        instance = "test-" + uuid.uuid4().hex
        container = {"Image": image, "Config": {"User": f"{os.getuid()}:{os.getgid()}",
                  "Labels": {"eros.forge.workspace": str(ROOT), "eros.forge.instance": instance}, "Env": []},
                  "Mounts": [], "HostConfig": {"NetworkMode": "host", "Privileged": False,
                  "CapAdd": [], "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"]},
                  "State": {"Running": True}}
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(os.environ, {"HOME": temporary, "FORGE_INSTANCE": instance}), \
             patch.object(forge_container, "workspace_root", return_value=ROOT), \
             patch.object(forge_container, "metadata_mounts", return_value=[]), \
             patch.object(forge_container, "docker", side_effect=lambda *args:
                          (json.dumps([]) if args[-1] == "{{json .Config.Env}}" else image + " linux/amd64")
                          if args[0] == "image" else "" if args[0] == "ps" else json.dumps([container])), \
             redirect_stderr(io.StringIO()) as stderr:
            key = hashlib.sha256(json.dumps([str(ROOT), image, os.getuid(), os.getgid(), instance]).encode()).hexdigest()[:20]
            state = Path(temporary) / ".cache/eros-forge" / key
            container["Config"]["Env"] = ["HOME=" + str(state / "home"), "PYTHONDONTWRITEBYTECODE=1"]
            with self.assertRaises(SystemExit) as exit_status:
                forge_container.main("bazel", ["query", "//..."])
        self.assertEqual(exit_status.exception.code, 1)
        self.assertIn("unexpected mounts", stderr.getvalue())

    def test_recursive_tmp_home_is_rejected(self):
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary, \
             patch.dict(os.environ, {"HOME": temporary}), \
             patch.object(forge_container, "workspace_root", return_value=ROOT), \
             patch.object(forge_container, "docker", side_effect=lambda *args:
                          json.dumps([]) if args[-1] == "{{json .Config.Env}}" else image + " linux/amd64"), \
             redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as exit_status:
                forge_container.main("bazel", ["query", "//..."])
        self.assertEqual(exit_status.exception.code, 1)
        self.assertIn("HOME must not be inside /tmp/kilo", stderr.getvalue())

    def test_parallel_instance_same_workspace_is_rejected(self):
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(os.environ, {"HOME": temporary, "FORGE_INSTANCE": "parallel"}), \
             patch.object(forge_container, "workspace_root", return_value=ROOT), \
             patch.object(forge_container, "metadata_mounts", return_value=[]), \
             patch.object(forge_container, "docker", side_effect=lambda *args:
                          "eros-forge-other" if args[0] == "ps" else
                          json.dumps([]) if args[-1] == "{{json .Config.Env}}" else image + " linux/amd64"), \
             redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as exit_status:
                forge_container.main("bazel", ["build", "//..."])
        self.assertEqual(exit_status.exception.code, 1)
        self.assertIn("Another Forge instance is running", stderr.getvalue())

    @unittest.skipUnless(os.environ.get("FORGE_TEST_DOCKER") == "1", "set FORGE_TEST_DOCKER=1 for Docker integration")
    def test_host_and_shell_reuse_one_server(self):
        directory, workspace = temporary_workspace()
        instance = "test-" + uuid.uuid4().hex
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        key = hashlib.sha256(json.dumps([str(workspace), image, os.getuid(), os.getgid(), instance]).encode()).hexdigest()[:20]
        name = "eros-forge-" + key
        state = Path.home() / ".cache/eros-forge" / key
        env = dict(os.environ, FORGE_INSTANCE=instance)
        try:
            def run(command, input=None):
                result = subprocess.run(command, input=input, text=True, capture_output=True, cwd=workspace,
                                        env=env, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()

            pid = run([str(ROOT / "forge-bazel"), "info", "server_pid"])
            self.assertTrue(pid.isdigit())
            self.assertEqual(run([str(ROOT / "forge-bazel"), "info", "server_pid"]), pid)
            output = run([str(ROOT / "forge-shell")], input="pwd\nbazel info server_pid\n")
            self.assertEqual(output.splitlines(), [str(workspace), pid])
            result = subprocess.run([str(ROOT / "forge-bazel"), "--output_base=/unmounted/base", "query", "//..."],
                                    cwd=workspace, env=env, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mounted workspace", result.stderr)
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            if state.is_dir():
                shutil.rmtree(state)
            directory.cleanup()

    @unittest.skipUnless(os.environ.get("FORGE_TEST_DOCKER") == "1", "set FORGE_TEST_DOCKER=1 for Docker integration")
    def test_modified_installed_tool_is_rejected(self):
        directory, workspace = temporary_workspace()
        instance = "tamper-" + uuid.uuid4().hex
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        key = hashlib.sha256(json.dumps([str(workspace), image, os.getuid(), os.getgid(), instance]).encode()).hexdigest()[:20]
        name = "eros-forge-" + key
        state = Path.home() / ".cache/eros-forge" / key
        env = dict(os.environ, FORGE_INSTANCE=instance)
        command = [str(ROOT / "forge-bazel"), "info", "server_pid"]
        try:
            first = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(first.returncode, 0, first.stderr)
            subprocess.run(["docker", "exec", "--user", "0", name, "sh", "-c", "printf x >> /usr/bin/m4"],
                           capture_output=True, check=True, timeout=30)
            second = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True, timeout=180)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("differs from reviewed baseline", second.stderr)
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            if state.is_dir():
                shutil.rmtree(state)
            directory.cleanup()

    @unittest.skipUnless(os.environ.get("FORGE_TEST_DOCKER") == "1", "set FORGE_TEST_DOCKER=1 for Docker integration")
    def test_pipe_signal_does_not_stop_other_container_sessions(self):
        directory, workspace = temporary_workspace()
        instance = "signal-" + uuid.uuid4().hex
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        key = hashlib.sha256(json.dumps([str(workspace), image, os.getuid(), os.getgid(), instance]).encode()).hexdigest()[:20]
        name = "eros-forge-" + key
        state = Path.home() / ".cache/eros-forge" / key
        env = dict(os.environ, FORGE_INSTANCE=instance)
        process = None
        try:
            process = subprocess.Popen([str(ROOT / "forge-shell")], cwd=workspace, env=env,
                                       text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process.stdin.write("exec sleep 30\n")
            process.stdin.flush()
            deadline = time.monotonic() + 30
            while not list((state / "tmp").glob("exec-*.pid")) and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(list((state / "tmp").glob("exec-*.pid")), "No container exec PID was published")
            time.sleep(0.1)
            process.send_signal(signal.SIGTERM)
            self.assertNotEqual(process.wait(timeout=10), 0)
            survivor = subprocess.run([str(ROOT / "forge-shell")], input="pwd\n", cwd=workspace, env=env,
                                      text=True, capture_output=True, timeout=180)
            self.assertEqual(survivor.returncode, 0, survivor.stderr)
            self.assertEqual(survivor.stdout.strip(), str(workspace))
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if process:
                process.stdin.close()
                process.stdout.close()
                process.stderr.close()
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            if state.is_dir():
                shutil.rmtree(state)
            directory.cleanup()

    @unittest.skipUnless(os.environ.get("FORGE_TEST_DOCKER") == "1", "set FORGE_TEST_DOCKER=1 for Docker integration")
    def test_workspace_bazelrc_cannot_redirect_output_base(self):
        directory, workspace = temporary_workspace()
        instance = "rc-" + uuid.uuid4().hex
        image = json.loads((ROOT / "docker/image.lock.json").read_text())["image"]
        key = hashlib.sha256(json.dumps([str(workspace), image, os.getuid(), os.getgid(), instance]).encode()).hexdigest()[:20]
        name = "eros-forge-" + key
        state = Path.home() / ".cache/eros-forge" / key
        (workspace / ".bazelrc").write_text("startup --output_base=/tmp/kilo/forge-rc-" + uuid.uuid4().hex + "\n")
        try:
            result = subprocess.run([str(ROOT / "forge-bazel"), "info", "workspace"], cwd=workspace,
                                    env=dict(os.environ, FORGE_INSTANCE=instance), capture_output=True, text=True,
                                    timeout=180)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Effective Bazel output base escapes this instance", result.stderr)
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            if state.is_dir():
                shutil.rmtree(state)
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
