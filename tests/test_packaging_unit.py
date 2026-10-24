"""Packaging validation using real ELF objects and isolated temporary inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_runner import ROOT


SPEC = importlib.util.spec_from_file_location("forge_packaging_driver", ROOT / "bazel/packaging/driver.py")
driver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = driver
SPEC.loader.exec_module(driver)


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="forge-packaging-unit-", dir="/tmp/kilo")
        cls.root = Path(cls.temporary.name)
        cls.lib = cls.root / "lib"
        cls.bin = cls.root / "bin"
        cls.lib.mkdir()
        cls.bin.mkdir()
        (cls.root / "private.c").write_text("int forge_unit_value(void) { return 7; }\n")
        (cls.root / "main.c").write_text(
            "extern int forge_unit_value(void);\n"
            "int main(void) { return forge_unit_value() == 7 ? 0 : 1; }\n"
        )
        compiler = shutil.which("gcc-13") or shutil.which("gcc")
        subprocess.run([
            compiler, "-g", "-fPIC", "-shared", "-Wl,--build-id", "-Wl,-soname,libforge_unit.so.1",
            "-Wl,-rpath,$ORIGIN", cls.root / "private.c", "-o", cls.lib / "libforge_unit.so.1.0",
        ], check=True, capture_output=True)
        (cls.lib / "libforge_unit.so.1").symlink_to("libforge_unit.so.1.0")
        (cls.lib / "libforge_unit.so").symlink_to("libforge_unit.so.1")
        subprocess.run([
            compiler, "-g", "-Wl,--build-id", cls.root / "main.c", f"-L{cls.lib}", "-lforge_unit",
            "-Wl,-rpath,$ORIGIN/../lib", "-o", cls.bin / "app",
        ], check=True, capture_output=True)
        cls.debug = cls.root / "app.debug"
        subprocess.run(["objcopy", "--only-keep-debug", cls.bin / "app", cls.debug], check=True, capture_output=True)
        cls.machine = driver.inspect_elf(cls.bin / "app")["architecture"]
        cls.preset = "linux_x86_64" if cls.machine == "amd64" else "linux_arm64"
        cls.environment = {"toolchains": {"native": {"runtime_sonames": ["libc.so.6"]}}}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="forge-packaging-case-", dir="/tmp/kilo")
        self.directory = Path(self.work.name)

    def tearDown(self):
        self.work.cleanup()

    def resource(self, name, content="unique"):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def entries(self):
        return driver.collect_entries([
            {"source": str(self.bin), "destination": "bin"},
            {"source": str(self.lib), "destination": "lib"},
        ])

    def test_collision_is_fatal(self):
        first = self.resource("a", "first")
        second = self.resource("b", "second")
        with self.assertRaisesRegex(driver.PackagingError, "collision"):
            driver.collect_entries([
                {"source": str(first), "destination": "share/value"},
                {"source": str(second), "destination": "share/value"},
            ])

    def test_identical_mapping_can_be_aggregated_twice(self):
        source = self.resource("value")
        mapping = {"source": str(source), "destination": "share/value"}
        self.assertEqual(len(driver.collect_entries([mapping, mapping])), 1)

    def test_public_export_copy_is_not_a_runtime_collision(self):
        first = self.resource("install/libfoo.so", "same artifact")
        second = self.resource("exports/libfoo.so", "same artifact")
        entries = driver.collect_entries([
            {"source": str(first), "destination": "lib/libfoo.so"},
            {"source": str(second), "destination": "lib/libfoo.so"},
        ])
        self.assertEqual(len(entries), 1)

    def test_soname_link_wins_over_identical_exported_copy(self):
        installed = self.directory / "installed"
        installed.mkdir()
        (installed / "libfoo.so.1.2").write_text("same library")
        (installed / "libfoo.so.1").symlink_to("libfoo.so.1.2")
        exported = self.resource("exports/libfoo.so.1", "same library")
        tree = {"source": str(installed), "destination": "lib"}
        copy = {"source": str(exported), "destination": "lib/libfoo.so.1"}
        for mappings in ([tree, copy], [copy, tree]):
            with self.subTest(mappings=mappings):
                entries = driver.collect_entries(mappings)
                self.assertEqual(entries["lib/libfoo.so.1"].link, "libfoo.so.1.2")

    def test_identical_content_but_different_mode_is_a_collision(self):
        first = self.resource("a", "same")
        second = self.resource("b", "same")
        first.chmod(0o644)
        second.chmod(0o755)
        with self.assertRaisesRegex(driver.PackagingError, "collision"):
            driver.collect_entries([
                {"source": str(first), "destination": "share/value"},
                {"source": str(second), "destination": "share/value"},
            ])

    def test_missing_input_is_fatal(self):
        with self.assertRaisesRegex(driver.PackagingError, "missing"):
            driver.collect_entries([{"source": str(self.directory / "absent"), "destination": "lib/plugin.so"}])

    def test_unsafe_destinations_rejected(self):
        source = self.resource("value")
        for destination in ("../value", "/tmp/value", "share/../../value", "share//value", "share/./value"):
            with self.subTest(destination=destination), self.assertRaises(driver.PackagingError):
                driver.collect_entries([{"source": str(source), "destination": destination}])

    def test_absolute_and_escaping_links_rejected(self):
        for index, target in enumerate(("/etc/passwd", "../../outside")):
            source = self.directory / f"link{index}"
            source.symlink_to(target)
            with self.assertRaisesRegex(driver.PackagingError, "escape"):
                driver.collect_entries([{"source": str(source), "destination": "lib/plugin.so"}])

    def test_soname_chain_is_preserved(self):
        entries = self.entries()
        self.assertEqual(entries["lib/libforge_unit.so"].link, "libforge_unit.so.1")
        self.assertEqual(entries["lib/libforge_unit.so.1"].link, "libforge_unit.so.1.0")
        self.assertEqual(driver.resolve_entry(entries, "lib/libforge_unit.so").path, "lib/libforge_unit.so.1.0")

    def test_link_cycle_rejected(self):
        (self.directory / "a").symlink_to("b")
        (self.directory / "b").symlink_to("a")
        with self.assertRaisesRegex(driver.PackagingError, "cycle"):
            driver.collect_entries([{"source": str(self.directory), "destination": "lib"}])

    def test_real_elf_architecture_validation(self):
        entries = self.entries()
        driver.validate_architecture(entries, self.machine)
        for architecture in ("all", "amd64" if self.machine == "arm64" else "arm64", "unknown"):
            with self.subTest(architecture=architecture), self.assertRaises(driver.PackagingError):
                driver.validate_architecture(entries, architecture)

    def test_resource_only_all(self):
        entries = driver.collect_entries([{"source": str(self.resource("value")), "destination": "share/value"}])
        driver.validate_architecture(entries, "all")

    def test_runtime_closure_is_relative_and_complete(self):
        entries = self.entries()
        metadata = driver.validate_elf_closure(entries, self.environment, self.preset)
        self.assertIn("bin/app", metadata)
        self.assertIn("libforge_unit.so.1", metadata["bin/app"]["needed"])
        missing = {name: entry for name, entry in entries.items() if not name.startswith("lib/")}
        with self.assertRaisesRegex(driver.PackagingError, "missing private runtime dependency"):
            driver.validate_elf_closure(missing, self.environment, self.preset)

    def test_no_implicit_host_runtime_boundary(self):
        with self.assertRaisesRegex(driver.PackagingError, "runtime SONAME boundary"):
            driver.validate_elf_closure(self.entries(), {})

    def test_malformed_elf_is_not_an_architecture_independent_file(self):
        source = self.directory / "broken"
        source.write_bytes(b"\x7fELFgarbage")
        with self.assertRaisesRegex(driver.PackagingError, "malformed ELF"):
            driver.inspect_elf(source)

    def debug_manifest(self, debug=None):
        binary = self.bin / "app"
        debug = debug or self.debug
        return {"binaries": [{
            "binary": str(binary), "debug_file": str(debug),
            "build_id": driver.inspect_elf(binary)["build_id"],
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "debug_sha256": hashlib.sha256(debug.read_bytes()).hexdigest(),
        }]}

    def test_correct_debug_identity(self):
        driver.validate_debug_manifest(self.debug_manifest())

    def test_wrong_debug_build_id_rejected(self):
        manifest = self.debug_manifest()
        manifest["binaries"][0]["build_id"] = "0" * 40
        with self.assertRaisesRegex(driver.PackagingError, "mismatch"):
            driver.validate_debug_manifest(manifest)

    def test_debug_digest_damage_rejected_even_with_same_build_id(self):
        debug = self.directory / "app.debug"
        shutil.copy2(self.debug, debug)
        manifest = self.debug_manifest(debug)
        with debug.open("ab") as output:
            output.write(b"damaged-content")
        self.assertEqual(driver.inspect_elf(debug)["build_id"], manifest["binaries"][0]["build_id"])
        with self.assertRaisesRegex(driver.PackagingError, "mismatch|digest|sha256"):
            driver.validate_debug_manifest(manifest)

    def test_version_precedence(self):
        self.assertEqual(driver.resolve_version("1.0", {"DEB_VERSION": "2.0"}, "3.0"), "1.0")
        self.assertEqual(driver.resolve_version("", {"DEB_VERSION": "2.0"}, "3.0"), "2.0")
        self.assertEqual(driver.resolve_version("", {}, "3.0"), "3.0")
        self.assertEqual(driver.resolve_version("", {}, ""), "0.1.0")
        with self.assertRaises(driver.PackagingError):
            driver.resolve_version("1.0\nInjected: value")

    def test_resource_archives_are_deterministic(self):
        source = self.resource("resource")
        outputs = []
        for name in ("first", "second"):
            output = self.directory / (name + ".tar.gz")
            driver.export_package({
                "entries": [{"source": str(source), "destination": "share/resource", "explicit": True}],
                "package": "forge-unit", "preset": "linux_arm64", "package_dir": "opt/eros/forge-unit",
                "manifest": str(self.directory / (name + ".json")), "output": str(output),
            }, {})
            outputs.append(output.read_bytes())
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
