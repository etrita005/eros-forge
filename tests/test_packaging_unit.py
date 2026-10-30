"""Packaging validation using real ELF objects and isolated temporary inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
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

    def test_external_deb_library_is_checked_and_not_bundled(self):
        a_tar = self.directory / "a.tar.gz"
        a_manifest = self.directory / "a.json"
        a_deb = self.directory / "a.deb"
        a_deb_manifest = self.directory / "a-deb.json"
        driver.export_package({
            "entries": [{"source": str(self.lib), "destination": "lib"}],
            "package": "forge-unit-a", "package_dir": "opt/eros/forge-unit-a", "preset": self.preset,
            "manifest": str(a_manifest), "output": str(a_tar),
        }, self.environment)
        driver.build_deb({
            "data": str(a_tar), "runtime_manifest": str(a_manifest), "package": "forge-unit-a",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(a_deb), "manifest": str(a_deb_manifest),
        })
        binary = self.directory / "app"
        compiler = shutil.which("gcc-13") or shutil.which("gcc")
        subprocess.run([
            compiler, self.root / "main.c", f"-L{self.lib}", "-lforge_unit",
            "-Wl,-rpath,$ORIGIN/../../forge-unit-a/lib", "-o", binary,
        ], check=True, capture_output=True)
        b_tar = self.directory / "b.tar.gz"
        b_manifest = self.directory / "b.json"
        spec = {
            "entries": [{"source": str(binary), "destination": "bin/app"},
                        {"source": str(self.lib), "destination": "lib"}],
            "external_packages": [{"deb": str(a_deb), "payload": str(a_tar), "manifest": str(a_deb_manifest)}],
            "package": "forge-unit-b", "package_dir": "opt/eros/forge-unit-b", "preset": self.preset,
            "manifest": str(b_manifest), "output": str(b_tar),
        }
        driver.export_package(spec, self.environment)
        with tarfile.open(b_tar) as archive:
            names = archive.getnames()
        self.assertIn("opt/eros/forge-unit-b/bin/app", names)
        self.assertFalse(any("forge_unit.so" in name for name in names))
        self.assertEqual(json.loads(b_manifest.read_text())["external_packages"], [
            {"package": "forge-unit-a", "version": "1.0.0", "architecture": self.machine,
             "deb_sha256": hashlib.sha256(a_deb.read_bytes()).hexdigest(),
             "payload_sha256": hashlib.sha256(a_tar.read_bytes()).hexdigest()},
        ])

        deb_spec = {
            "data": str(b_tar), "runtime_manifest": str(b_manifest), "package": "forge-unit-b",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(self.directory / "b.deb"), "manifest": str(self.directory / "b-deb.json"),
        }
        with self.assertRaisesRegex(driver.PackagingError, "Depends"):
            driver.build_deb(deb_spec)
        deb_spec["depends"] = ["forge-unit-a (= 2.0.0)"]
        with self.assertRaisesRegex(driver.PackagingError, "Depends"):
            driver.build_deb(deb_spec)
        deb_spec["depends"] = ["forge-unit-a (= 1.0.0)"]
        deb_spec["architecture"] = "arm64" if self.machine == "amd64" else "amd64"
        with self.assertRaisesRegex(driver.PackagingError, "architecture"):
            driver.build_deb(deb_spec)
        deb_spec["architecture"] = self.machine
        driver.build_deb(deb_spec)
        self.assertTrue(Path(deb_spec["output"]).is_file())
        deb_spec["dependency_manifests"] = [str(a_deb_manifest)]
        with self.assertRaisesRegex(driver.PackagingError, "duplicate or conflicting"):
            driver.build_deb(deb_spec)
        deb_spec["depends"] = []
        driver.build_deb(deb_spec)
        self.assertEqual(subprocess.run(["dpkg-deb", "--field", deb_spec["output"], "Depends"],
                                        check=True, capture_output=True, text=True).stdout.strip(),
                         "forge-unit-a (= 1.0.0)")
        deb_spec["depends"] = ["libc6 (>= 2.31)"]
        driver.build_deb(deb_spec)
        self.assertEqual(subprocess.run(["dpkg-deb", "--field", deb_spec["output"], "Depends"],
                                        check=True, capture_output=True, text=True).stdout.strip(),
                         "libc6 (>= 2.31), forge-unit-a (= 1.0.0)")
        deb_spec["depends"] = []
        unrelated = self.directory / "unrelated-runtime.json"
        unrelated.write_text(json.dumps({"package": "forge-unit-b", "external_packages": []}))
        with self.assertRaisesRegex(driver.PackagingError, "does not match"):
            driver.build_deb(dict(deb_spec, runtime_manifest=str(unrelated)))

        generated = self.directory / "app.runtime"
        generated.mkdir()
        (generated / "runtime_manifest.json").write_text(json.dumps({
            "schema_version": 1, "label": "//b:app", "package": "app", "install_root": "",
            "files": [{"path": "bin/app"}, {"path": "lib/libforge_unit.so.1"}],
        }))
        with_manifest = dict(spec, entries=spec["entries"] + [
            {"source": str(generated / "runtime_manifest.json"), "destination": "runtime_manifest.json", "explicit": True},
        ])
        driver.export_package(with_manifest, self.environment)
        with tarfile.open(b_tar) as archive:
            document = json.load(archive.extractfile("opt/eros/forge-unit-b/runtime_manifest.json"))
        self.assertEqual(document["files"], [{"path": "bin/app"}])
        self.assertEqual(document["external_packages"][0]["package"], "forge-unit-a")
        custom = self.directory / "runtime_manifest.json"
        custom.write_text("user-defined metadata")
        driver.export_package(dict(spec, entries=spec["entries"] + [
            {"source": str(custom), "destination": "runtime_manifest.json", "explicit": True},
        ]), self.environment)
        with tarfile.open(b_tar) as archive:
            self.assertEqual(archive.extractfile("opt/eros/forge-unit-b/runtime_manifest.json").read(),
                             b"user-defined metadata")

        without_runpath = dict(spec, entries=[{"source": str(self.bin / "app"), "destination": "bin/app"},
                                               {"source": str(self.lib), "destination": "lib"}])
        with self.assertRaisesRegex(driver.PackagingError, "missing private runtime dependency"):
            driver.export_package(without_runpath, self.environment)
        corrupted = self.directory / "other.so"
        shutil.copy2(self.lib / "libforge_unit.so.1.0", corrupted)
        with corrupted.open("ab") as stream:
            stream.write(b"different")
        different = dict(spec, entries=[{"source": str(binary), "destination": "bin/app"},
                                        {"source": str(corrupted), "destination": "lib/libforge_unit.so.1.0"},
                                        {"source": str(self.lib / "libforge_unit.so.1"), "destination": "lib/libforge_unit.so.1"}])
        with self.assertRaisesRegex(driver.PackagingError, "differs from external Debian package"):
            driver.export_package(different, self.environment)
        with self.assertRaisesRegex(driver.PackagingError, "missing from the Bazel runtime closure"):
            driver.export_package(dict(spec, entries=[{"source": str(binary), "destination": "bin/app"}]), self.environment)

        duplicate = dict(spec, entries=[{"source": str(binary), "destination": "bin/app"},
                                        {"source": str(self.lib), "destination": "lib"},
                                        {"source": str(self.lib / "libforge_unit.so.1.0"),
                                         "destination": "share/renamed-copy", "explicit": True}])
        with self.assertRaisesRegex(driver.PackagingError, "also bundled"):
            driver.export_package(duplicate, self.environment)

        empty = dict(spec, entries=[])
        with self.assertRaisesRegex(driver.PackagingError, "missing from the Bazel runtime closure"):
            driver.export_package(empty, self.environment)

        extra = self.directory / "a-libraries"
        shutil.copytree(self.lib, extra, symlinks=True)
        plugin = extra / "plugin.so"
        subprocess.run([compiler, "-shared", "-fPIC", self.root / "private.c", "-o", plugin],
                       check=True, capture_output=True)
        self.assertIsNone(driver.inspect_elf(plugin)["soname"])
        driver.export_package({
            "entries": [{"source": str(extra), "destination": "lib"}],
            "package": "forge-unit-a", "package_dir": "opt/eros/forge-unit-a", "preset": self.preset,
            "manifest": str(a_manifest), "output": str(a_tar),
        }, self.environment)
        driver.build_deb({
            "data": str(a_tar), "runtime_manifest": str(a_manifest), "package": "forge-unit-a",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(a_deb), "manifest": str(a_deb_manifest),
        })
        driver.export_package(spec, self.environment)
        (extra / "README").write_text("not a shared library")
        driver.export_package({
            "entries": [{"source": str(extra), "destination": "lib"}],
            "package": "forge-unit-a", "package_dir": "opt/eros/forge-unit-a", "preset": self.preset,
            "manifest": str(a_manifest), "output": str(a_tar),
        }, self.environment)
        driver.build_deb({
            "data": str(a_tar), "runtime_manifest": str(a_manifest), "package": "forge-unit-a",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(a_deb), "manifest": str(a_deb_manifest),
        })
        driver.export_package(dict(spec, entries=spec["entries"] + [
            {"source": str(extra / "README"), "destination": "share/README", "explicit": True},
        ]), self.environment)

        driver.build_deb({
            "data": str(a_tar), "runtime_manifest": str(a_manifest), "package": "forge-unit-a",
            "version": "2.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(a_deb), "manifest": str(a_deb_manifest),
        })
        with self.assertRaisesRegex(driver.PackagingError, "does not match"):
            driver.build_deb(deb_spec)
        driver.export_package(spec, self.environment)
        driver.build_deb(deb_spec)
        self.assertEqual(subprocess.run(["dpkg-deb", "--field", deb_spec["output"], "Depends"],
                                        check=True, capture_output=True, text=True).stdout.strip(),
                         "forge-unit-a (= 2.0.0)")

        c_tar = self.directory / "c.tar.gz"
        c_manifest = self.directory / "c.json"
        c_deb = self.directory / "c.deb"
        c_deb_manifest = self.directory / "c-deb.json"
        driver.export_package({
            "entries": [{"source": str(self.lib), "destination": "lib"}],
            "package": "forge-unit-c", "package_dir": "opt/eros/forge-unit-c", "preset": self.preset,
            "manifest": str(c_manifest), "output": str(c_tar),
        }, self.environment)
        driver.build_deb({
            "data": str(c_tar), "runtime_manifest": str(c_manifest), "package": "forge-unit-c",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(c_deb), "manifest": str(c_deb_manifest),
        })
        other_binary = self.directory / "app-c"
        subprocess.run([compiler, self.root / "main.c", f"-L{self.lib}", "-lforge_unit",
                        "-Wl,-rpath,$ORIGIN/../../forge-unit-c/lib", "-o", other_binary],
                       check=True, capture_output=True)
        multiple = dict(spec, entries=spec["entries"] + [{"source": str(other_binary), "destination": "bin/app-c"}],
                        external_packages=spec["external_packages"] + [
                            {"deb": str(c_deb), "payload": str(c_tar), "manifest": str(c_deb_manifest)},
                        ])
        driver.export_package(multiple, self.environment)
        driver.build_deb(dict(deb_spec, dependency_manifests=[str(a_deb_manifest), str(c_deb_manifest)]))
        self.assertEqual(subprocess.run(["dpkg-deb", "--field", deb_spec["output"], "Depends"],
                                        check=True, capture_output=True, text=True).stdout.strip(),
                         "forge-unit-a (= 2.0.0), forge-unit-c (= 1.0.0)")

        for suffix, value, package, payload, runtime_manifest, deb, deb_manifest, version in (
            ("a", 11, "forge-unit-a", a_tar, a_manifest, a_deb, a_deb_manifest, "2.0.0"),
            ("c", 17, "forge-unit-c", c_tar, c_manifest, c_deb, c_deb_manifest, "1.0.0"),
        ):
            library_dir = self.directory / f"{suffix}-collision-libraries"
            shutil.copytree(self.lib, library_dir, symlinks=True)
            source = self.resource(f"collision-{suffix}.c", f"int collision_value(void) {{ return {value}; }}\n")
            subprocess.run([compiler, "-shared", "-fPIC", "-Wl,-soname,libcollision.so.1",
                            source, "-o", library_dir / "libcollision.so.1.0"],
                           check=True, capture_output=True)
            driver.export_package({
                "entries": [{"source": str(library_dir), "destination": "lib"}],
                "package": package, "package_dir": "opt/eros/" + package, "preset": self.preset,
                "manifest": str(runtime_manifest), "output": str(payload),
            }, self.environment)
            driver.build_deb({
                "data": str(payload), "runtime_manifest": str(runtime_manifest), "package": package,
                "version": version, "architecture": self.machine, "preset": self.preset,
                "output": str(deb), "manifest": str(deb_manifest),
            })
        driver.export_package(multiple, self.environment)
        own_different = self.directory / "own-different.so"
        source = self.resource("collision-b.c", "int collision_value(void) { return 23; }\n")
        subprocess.run([compiler, "-shared", "-fPIC", "-Wl,-soname,libcollision.so.1",
                        source, "-o", own_different], check=True, capture_output=True)
        own_same = self.directory / "own-same.so"
        shutil.copy2(self.directory / "a-collision-libraries/libcollision.so.1.0", own_same)
        for owned, expected in ((own_different, 23), (own_same, 11)):
            with self.subTest(owned=owned):
                own_lib = self.directory / (owned.stem + "-lib")
                own_lib.mkdir()
                shutil.copy2(owned, own_lib / "libcollision.so.1.0")
                (own_lib / "libcollision.so.1").symlink_to("libcollision.so.1.0")
                (own_lib / "libcollision.so").symlink_to("libcollision.so.1")
                own_app = self.directory / (owned.stem + "-app")
                source = self.resource(owned.stem + "-app.c", "extern int collision_value(void);\n"
                                       f"int main(void) {{ return collision_value() == {expected} ? 0 : 1; }}\n")
                subprocess.run([compiler, source, f"-L{own_lib}", "-lcollision",
                                "-Wl,-rpath,$ORIGIN/../lib", "-o", own_app], check=True, capture_output=True)
                driver.export_package(dict(multiple, entries=multiple["entries"] + [
                    {"source": str(own_lib), "destination": "lib", "explicit": True},
                    {"source": str(own_app), "destination": "bin/own-app"},
                ]), self.environment)
                with tarfile.open(b_tar) as archive:
                    installed = archive.extractfile("opt/eros/forge-unit-b/lib/libcollision.so.1.0")
                    self.assertIsNotNone(installed)
                    self.assertEqual(installed.read(), owned.read_bytes())
                    with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
                        archive.extractall(directory, filter="data")
                        subprocess.run([str(Path(directory) / "opt/eros/forge-unit-b/bin/own-app")],
                                       check=True, capture_output=True)

    def test_external_transitive_library_is_not_bundled(self):
        compiler = shutil.which("gcc-13") or shutil.which("gcc")
        libraries = self.directory / "a-libraries"
        shutil.copytree(self.lib, libraries, symlinks=True)
        source = self.resource("forward.c", "extern int forge_unit_value(void);\n"
                               "int forge_forward_value(void) { return forge_unit_value(); }\n")
        subprocess.run([compiler, "-shared", "-fPIC", source, f"-L{libraries}", "-lforge_unit",
                        "-Wl,-soname,libforge_forward.so.1", "-Wl,-rpath,$ORIGIN",
                        "-o", libraries / "libforge_forward.so.1.0"], check=True, capture_output=True)
        (libraries / "libforge_forward.so.1").symlink_to("libforge_forward.so.1.0")
        (libraries / "libforge_forward.so").symlink_to("libforge_forward.so.1")
        self.assertIn("libforge_unit.so.1", driver.inspect_elf(libraries / "libforge_forward.so.1.0")["needed"])
        a_tar = self.directory / "a.tar.gz"
        a_manifest = self.directory / "a.json"
        a_deb = self.directory / "a.deb"
        a_deb_manifest = self.directory / "a-deb.json"
        driver.export_package({
            "entries": [{"source": str(libraries), "destination": "lib"}],
            "package": "forge-unit-a", "package_dir": "opt/eros/forge-unit-a", "preset": self.preset,
            "manifest": str(a_manifest), "output": str(a_tar),
        }, self.environment)
        driver.build_deb({
            "data": str(a_tar), "runtime_manifest": str(a_manifest), "package": "forge-unit-a",
            "version": "1.0.0", "architecture": self.machine, "preset": self.preset,
            "output": str(a_deb), "manifest": str(a_deb_manifest),
        })
        source = self.resource("forward_main.c", "extern int forge_forward_value(void);\n"
                               "int main(void) { return forge_forward_value() == 7 ? 0 : 1; }\n")
        binary = self.directory / "app"
        subprocess.run([compiler, source, f"-L{libraries}", "-lforge_forward",
                        f"-Wl,-rpath-link,{libraries}", "-Wl,-rpath,$ORIGIN/../../forge-unit-a/lib",
                        "-o", binary], check=True, capture_output=True)
        b_tar = self.directory / "b.tar.gz"
        driver.export_package({
            "entries": [{"source": str(binary), "destination": "bin/app"},
                        {"source": str(libraries), "destination": "lib"}],
            "external_packages": [{"deb": str(a_deb), "payload": str(a_tar), "manifest": str(a_deb_manifest)}],
            "package": "forge-unit-b", "package_dir": "opt/eros/forge-unit-b", "preset": self.preset,
            "manifest": str(self.directory / "b.json"), "output": str(b_tar),
        }, self.environment)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            with tarfile.open(b_tar) as archive:
                self.assertFalse(any("libforge_forward.so" in name or "libforge_unit.so" in name
                                     for name in archive.getnames()))
                archive.extractall(directory, filter="data")
            with tarfile.open(a_tar) as archive:
                archive.extractall(directory, filter="data")
            subprocess.run([str(Path(directory) / "opt/eros/forge-unit-b/bin/app")],
                           check=True, capture_output=True)

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
