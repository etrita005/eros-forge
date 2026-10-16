"""Negative identity tests do not modify installed tools, SDKs or the user home."""

import copy
from pathlib import Path
import tempfile
import unittest

import environment


class EnvironmentIdentityTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="forge-environment-", dir="/tmp/kilo")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_file_content_change_is_detected(self):
        support = self.root / "cc1plus"
        support.write_bytes(b"compiler support v1")
        old = environment.file_identity(support)
        support.write_bytes(b"compiler support v2")
        self.assertNotEqual(old, environment.file_identity(support))

    def test_tree_detects_added_and_removed_files(self):
        header = self.root / "header.h"
        before, _ = environment.tree_identity(self.root)
        header.write_text("int api();\n")
        after, _ = environment.tree_identity(self.root)
        self.assertNotEqual(before["sha256"], after["sha256"])
        header.unlink()
        self.assertEqual(before, environment.tree_identity(self.root)[0])

    def test_directory_symlink_identity_is_not_lost(self):
        for name in ["a", "b"]:
            (self.root / name).mkdir()
            (self.root / name / "header.h").write_text(name)
        link = self.root / "include"
        link.symlink_to("a", target_is_directory=True)
        before, _ = environment.tree_identity(self.root)
        link.unlink()
        link.symlink_to("b", target_is_directory=True)
        self.assertNotEqual(before, environment.tree_identity(self.root)[0])

    def manifest(self, identity):
        manifest = {
            "schema_version": 1, "gcc_major": "13",
            "expected_versions": {"bazel": "9.0.0", "cmake": "4.4.4", "conan": "2.25.2", "python_major": "3"},
            "tools": {name: {"version": version} for name, version in [("bazel", "9.0.0"), ("cmake", "4.4.4"), ("conan", "2.25.2"), ("python", "3.12.3")]},
            "toolchains": {}, "identities": [identity], "sdk": {"present": False},
        }
        manifest["environment_sha256"] = environment.digest(manifest)
        return manifest

    def test_stale_support_file_rejects_manifest(self):
        support = self.root / "libgcc.a"
        support.write_bytes(b"runtime old")
        manifest = self.manifest(environment.file_identity(support))
        support.write_bytes(b"runtime new")
        with self.assertRaisesRegex(ValueError, "installed environment identity mismatch"):
            environment.validate(manifest)

    def test_corrupted_manifest_is_rejected(self):
        manifest = self.manifest(environment.file_identity(self.root / "missing"))
        manifest["gcc_major"] = "14"
        with self.assertRaisesRegex(ValueError, "manifest digest mismatch"):
            environment.validate(manifest)

    def test_wrong_tool_version_is_rejected_even_with_valid_digest(self):
        manifest = self.manifest(environment.file_identity(self.root / "missing"))
        del manifest["environment_sha256"]
        manifest["tools"]["cmake"]["version"] = "3.31.0"
        manifest["environment_sha256"] = environment.digest(manifest)
        with self.assertRaisesRegex(ValueError, "controlled cmake version mismatch"):
            environment.validate(manifest)

    def test_manifest_cannot_override_committed_version_policy(self):
        manifest = self.manifest(environment.file_identity(self.root / "missing"))
        spec = {"expected_versions": copy.deepcopy(manifest["expected_versions"]), "gcc_major": "13"}
        spec["expected_versions"]["cmake"] = "4.4.5"
        with self.assertRaisesRegex(ValueError, "committed version policy"):
            environment.validate(manifest, spec)

    def test_sdk_runtime_must_match_the_compiler_runtime(self):
        runtime = self.root / "compiler-libc.so.6"
        runtime.write_bytes(b"controlled compiler runtime")
        sdk = self.root / "sdk"
        (sdk / "lib").mkdir(parents=True)
        manifest = {
            "sdk": {"present": True, "path": str(sdk)},
            "toolchains": {"cross_arm64": {"runtime_files": [dict(environment.file_identity(runtime), soname="libc.so.6")]}},
        }
        with self.assertRaisesRegex(ValueError, "SDK/runtime identity mismatch"):
            environment.check_sdk(manifest)
        (sdk / "lib/libc.so.6").write_bytes(runtime.read_bytes())
        environment.check_sdk(manifest)
        (sdk / "lib/libc.so.6").write_bytes(b"wrong SDK runtime")
        with self.assertRaisesRegex(ValueError, "SDK/runtime identity mismatch"):
            environment.check_sdk(manifest)


if __name__ == "__main__":
    unittest.main()
