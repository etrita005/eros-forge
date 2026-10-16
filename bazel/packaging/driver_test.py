"""Additional stdlib-only tests for archive and closure boundary cases."""

import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

import driver


def elf(machine=183):
    identification = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    header = struct.pack("<HHIQQQIHHHHHH", 1, machine, 1, 0, 0, 0, 0, 64, 56, 0, 64, 0, 0)
    return identification + header


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-packaging-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def file(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def debug_fixture(self):
        binary = self.file("install/lib/value.a", b"!<arch>\n" + driver._ar_member("value.o", elf()))
        debug = self.file("symbols/value.a.debug", b"!<arch>\n" + driver._ar_member("debug.o", elf()))
        source = self.file("symbols/sources/value.h", b"int value();\n")
        (source.parent / "alias.h").symlink_to(source.name)
        document = {
            "enabled": True,
            "binaries": [{"binary": "install/lib/value.a", "debug_file": "symbols/value.a.debug", "build_id": None,
                          "binary_sha256": driver._sha256(binary), "debug_sha256": driver._sha256(debug)}],
            "sources": {"directory": "symbols/sources", "files": [
                {"path": source.name, "sha256": driver._sha256(source)},
                {"path": "alias.h", "symlink": source.name},
            ]},
        }
        return document, binary, debug, source

    def test_architecture_all_rejects_elf_inside_static_archive(self):
        library = self.file("library.a", b"!<arch>\n" + driver._ar_member("member.o", elf()))
        entries = driver.collect_entries([{"source": str(library), "destination": "share/library.a"}])
        driver.validate_architecture(entries, "arm64")
        with self.assertRaisesRegex(driver.PackagingError, "Architecture=all"):
            driver.validate_architecture(entries, "all")
        with self.assertRaisesRegex(driver.PackagingError, "Architecture=amd64"):
            driver.validate_architecture(entries, "amd64")

    def test_dwarf5_skeleton_is_not_complete_standalone_symbols(self):
        strings = b"\0.shstrtab\0.debug_info\0"
        skeleton = struct.pack("<IHBBIQ", 16, 5, 4, 8, 0, 123)
        identification = b"\x7fELF\x02\x01\x01" + b"\0" * 9
        header = struct.pack("<HHIQQQIHHHHHH", 1, 183, 1, 0, 0, 64, 0, 64, 56, 0, 64, 3, 1)
        sections = b"\0" * 64
        sections += struct.pack("<IIQQQQIIQQ", 1, 3, 0, 0, 256, len(strings), 0, 0, 1, 0)
        sections += struct.pack("<IIQQQQIIQQ", 11, 1, 0, 0, 256 + len(strings), len(skeleton), 0, 0, 1, 0)
        binary = self.file("skeleton", identification + header + sections + strings + skeleton)
        metadata = driver.inspect_elf(binary)
        self.assertTrue(metadata["has_debug_info"])
        self.assertTrue(metadata["requires_external_dwarf"])

    def test_malformed_archive_rejected(self):
        library = self.file("bad.a", b"!<arch>\nmalformed header")
        entries = driver.collect_entries([{"source": str(library), "destination": "share/bad.a"}])
        with self.assertRaisesRegex(driver.PackagingError, "malformed static archive"):
            driver.validate_architecture(entries, "all")

    def test_bazel_alias_deduplicates_without_flattening_soname_links(self):
        real = self.file("library/libvalue.so.1.2", elf())
        (real.parent / "libvalue.so.1").symlink_to(real.name)
        exported = self.root / "exported.so"
        exported.symlink_to(real)
        entries = driver.collect_entries([
            {"source": str(real.parent), "destination": "lib"},
            {"source": str(exported), "destination": "lib/libvalue.so.1", "dereference": True},
        ])
        self.assertEqual(entries["lib/libvalue.so.1"].link, "libvalue.so.1.2")

    def test_unselected_shared_alternative_pruned_but_data_plugin_kept(self):
        binary = self.file("app", elf())
        library = self.file("alternative.so", elf())
        plugin = self.file("plugin.so", elf())
        mappings = [
            {"source": str(binary), "destination": "bin/app"},
            {"source": str(library), "destination": "lib/alternative.so"},
            {"source": str(plugin), "destination": "lib/plugin.so", "explicit": True},
        ]
        selected = driver.prune_runtime_entries(driver.collect_entries(mappings), mappings)
        self.assertEqual(set(selected), {"bin/app", "lib/plugin.so"})

    def test_explicit_plugin_alias_roots_real_elf_after_export_copy_dedup(self):
        binary = self.file("app", elf())
        plugin = self.file("libraries/libplugin.so.1.2", elf())
        (plugin.parent / "libplugin.so.1").symlink_to(plugin.name)
        (plugin.parent / "libplugin.so").symlink_to("libplugin.so.1")
        exported = self.file("exports/libplugin.so.1", plugin.read_bytes())
        mappings = [
            {"source": str(binary), "destination": "bin/app"},
            {"source": str(plugin.parent), "destination": "lib"},
            {"source": str(exported), "destination": "lib/libplugin.so.1", "explicit": True},
        ]
        selected = driver.prune_runtime_entries(driver.collect_entries(mappings), mappings)
        self.assertEqual(selected["lib/libplugin.so.1"].link, "libplugin.so.1.2")
        self.assertIn("lib/libplugin.so.1.2", selected)
        self.assertIn("lib/libplugin.so", selected)

    def test_deb_symlink_cannot_escape_one_private_package_into_another(self):
        payload = self.root / "payload.tar"
        with tarfile.open(payload, "w") as archive:
            link = tarfile.TarInfo("opt/eros/first/lib/escape")
            link.type, link.linkname = tarfile.SYMTYPE, "../../second/marker"
            archive.addfile(link)
            marker = tarfile.TarInfo("opt/eros/second/marker")
            marker.size = 1
            archive.addfile(marker, io.BytesIO(b"x"))
        with self.assertRaisesRegex(driver.PackagingError, "private package root"):
            list(driver._read_payload(payload))

    def test_debug_disabled_manifest_is_not_a_symbols_claim(self):
        self.assertFalse(driver.validate_debug_manifest({"enabled": False, "binaries": []})["enabled"])
        with self.assertRaisesRegex(driver.PackagingError, "empty debug identity"):
            driver.validate_debug_manifest({"enabled": True, "binaries": []})

    def test_source_alias_inventory_validates_link_identity_and_containment(self):
        document, _, _, source = self.debug_fixture()
        driver.validate_debug_manifest(document, binary_root=self.root, debug_root=self.root)
        alias = source.parent / "alias.h"
        alias.unlink()
        alias.symlink_to("../../install/lib/value.a")
        document["sources"]["files"][1]["symlink"] = "../../install/lib/value.a"
        with self.assertRaisesRegex(driver.PackagingError, "symlink.*escape"):
            driver.validate_debug_manifest(document, binary_root=self.root, debug_root=self.root)

    def test_nonempty_debug_export_preserves_binary_and_source_associations(self):
        document, binary, debug, _ = self.debug_fixture()
        original_manifest = self.file("value.debug_manifest.json", json.dumps(document).encode())
        output = self.root / "symbols.tar.gz"
        driver.export_debug_package({
            "entries": [{"source": str(debug.parent), "destination": "symbols/0/value.debug", "explicit": True}],
            "runtime_entries": [{"source": str(binary), "destination": "lib/value.a"}],
            "debug_manifests": [str(original_manifest)], "package": "symbols", "preset": "linux_arm64",
            "package_dir": "", "separate_debug": True, "output": str(output), "manifest": str(self.root / "manifest.json"),
        }, {})
        destination = self.root / "extracted"
        with tarfile.open(output) as archive:
            archive.extractall(destination, filter="data")
        identity = json.loads((destination / "debug_manifest.json").read_text())
        self.assertEqual(identity["binaries"][0]["binary"], "lib/value.a")
        self.assertEqual(identity["sources"][0]["directory"], "symbols/0/value.debug/sources")
        driver.validate_debug_manifest(identity, binary_root=self.root / "install", debug_root=destination)

    def test_external_repository_sandbox_transport_is_not_a_payload_link(self):
        artifact = self.file("repository/sub/value", b"resource")
        working = self.root / "sandbox/execroot/_main"
        transport = working / "external/repository/sub/value"
        transport.parent.mkdir(parents=True)
        transport.symlink_to(artifact)
        previous = Path.cwd()
        os.chdir(working)
        self.addCleanup(os.chdir, previous)
        entries = driver.collect_entries([{"source": "external/repository/sub/value", "destination": "share/value"}])
        self.assertIsNone(entries["share/value"].link)
        self.assertEqual(entries["share/value"].source.read_bytes(), b"resource")
        artifact.unlink()
        artifact.symlink_to(self.root / "private-host-file")
        with self.assertRaisesRegex(driver.PackagingError, "symlink escape"):
            driver.collect_entries([{"source": "external/repository/sub/value", "destination": "share/value"}])

    def test_explicit_empty_resource_directory_is_preserved(self):
        empty = self.root / "empty"
        empty.mkdir()
        entries = driver.collect_entries([{"source": str(empty), "destination": "share/empty"}])
        with tarfile.open(fileobj=io.BytesIO(driver._tar_bytes(entries))) as archive:
            self.assertTrue(archive.getmember("share/empty").isdir())

    def test_debug_archive_disambiguates_independent_symbol_directories(self):
        first = self.file("first/symbol.debug", b"first")
        second = self.file("second/symbol.debug", b"second")
        mappings = [
            {"source": str(first.parent), "destination": "symbols/0/first", "explicit": True},
            {"source": str(second.parent), "destination": "symbols/1/second", "explicit": True},
        ]
        output, manifest = self.root / "symbols.tar.gz", self.root / "manifest.json"
        driver.export_debug_package({
            "entries": mappings, "runtime_entries": [], "debug_manifests": [],
            "package": "symbols", "preset": "linux_arm64", "package_dir": "", "separate_debug": False,
            "output": str(output), "manifest": str(manifest),
        }, {})
        with tarfile.open(output) as archive:
            self.assertEqual(archive.extractfile("symbols/0/first/symbol.debug").read(), b"first")
            self.assertEqual(archive.extractfile("symbols/1/second/symbol.debug").read(), b"second")
            identity = json.load(archive.extractfile("debug_manifest.json"))
            self.assertTrue(identity["requires_matching_payload"])
            self.assertFalse(identity["enabled"])


if __name__ == "__main__":
    unittest.main()
