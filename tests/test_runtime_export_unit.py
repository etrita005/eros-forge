"""Exercise the runtime-export CLI with real target ELF files, without running them."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from test_runner import ROOT


EXPORTER = ROOT / "bazel/toolchain/export_runtime.sh"


class RuntimeExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("aarch64-linux-gnu-gcc-13")
        if not cls.compiler:
            raise unittest.SkipTest("Runtime-export fixtures require the controlled AArch64 GCC 13")
        cls.fixture = tempfile.TemporaryDirectory(prefix="forge-runtime-fixture-", dir="/tmp/kilo")
        cls.addClassCleanup(cls.fixture.cleanup)
        root = Path(cls.fixture.name)
        (root / "bin").mkdir()
        libraries = root / "lib"
        libraries.mkdir()
        source = root / "source.c"
        source.write_text("int forge_runtime_fixture(void) { return 17; }\n")
        for name in ("libc.so.6", "libm.so.6", "libgcc_s.so.1", "ld-linux-aarch64.so.1", "libsupport.so.1"):
            subprocess.run([cls.compiler, "-shared", "-fPIC", "-nostdlib", "-Wl,-soname," + name,
                            str(source), "-o", str(libraries / name)], check=True, capture_output=True)
        source.write_text("extern int forge_runtime_fixture(void);\n"
                          "int forge_cpp_fixture(void) { return forge_runtime_fixture(); }\n")
        subprocess.run([cls.compiler, "-shared", "-fPIC", "-nostdlib", "-Wl,-soname,libstdc++.so.6",
                        str(source), "-L" + str(libraries), "-Wl,--no-as-needed", "-l:libsupport.so.1",
                        "-o", str(libraries / "libstdc++.so.6.0.1")], check=True, capture_output=True)
        (libraries / "libstdc++.so.6").symlink_to("libstdc++.so.6.0.1")
        compiler = root / "bin" / "gcc"
        compiler.write_text("""#!/usr/bin/env bash
set -eu
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
case "$1" in
    -dumpmachine) printf '%s\\n' aarch64-linux-gnu ;;
    -dumpfullversion) printf '%s\\n' 13.3.0 ;;
    -print-sysroot) printf '%s\\n' "$root" ;;
    -print-file-name=*)
        name=${1#*=}
        if [[ -f "$root/lib/$name" ]]; then
            printf '%s\\n' "$root/lib/$name"
        else
            printf '%s\\n' "$name"
        fi ;;
    *) exit 2 ;;
esac
""")
        compiler.chmod(0o755)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="forge-runtime-test-", dir="/tmp/kilo")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.toolchain = self.root / "tool chain"
        shutil.copytree(self.fixture.name, self.toolchain, symlinks=True)
        self.output = self.root / "runtime archive.tar.gz"

    def export(self, **kwargs):
        return subprocess.run(["bash", str(EXPORTER), "--compiler", str(self.toolchain / "bin/gcc"),
                               "--output", str(self.output)], text=True, capture_output=True, **kwargs)

    def test_exports_runtime_closure_relative_sonames_and_checksums(self):
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tarfile.open(self.output) as archive:
            names = archive.getnames()
            prefix = "opt/eros/"
            for name in ("libc.so.6", "libm.so.6", "libgcc_s.so.1", "ld-linux-aarch64.so.1",
                         "libstdc++.so.6.0.1", "libsupport.so.1"):
                self.assertIn(prefix + "lib/" + name, names)
            alias = archive.getmember(prefix + "lib/libstdc++.so.6")
            self.assertTrue(alias.issym())
            self.assertEqual(alias.linkname, "libstdc++.so.6.0.1")
            self.assertIn(prefix + "TOOLCHAIN", names)
            checksums = archive.extractfile(prefix + "SHA256SUMS").read().decode()
            for line in checksums.splitlines():
                checksum, path = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(archive.extractfile(prefix + path).read()).hexdigest(), checksum)
            for member in archive.getmembers():
                self.assertFalse(member.name.startswith("/"))
                self.assertNotIn("..", Path(member.name).parts)
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))

    def test_same_inputs_produce_identical_archives_despite_output_name_and_umask(self):
        first = self.export()
        self.assertEqual(first.returncode, 0, first.stderr)
        contents = self.output.read_bytes()
        self.output = self.root / "second.tgz"
        second = self.export(preexec_fn=lambda: os.umask(0o077))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.output.read_bytes(), contents)

    def test_missing_core_runtime_fails_without_publishing_archive(self):
        (self.toolchain / "lib/libstdc++.so.6").unlink()
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required runtime library not found: libstdc++.so.6", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_transitive_runtime_fails_without_host_fallback(self):
        (self.toolchain / "lib/libsupport.so.1").unlink()
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required runtime library not found: libsupport.so.1", result.stderr)
        self.assertFalse(self.output.exists())

    def test_payload_basename_does_not_satisfy_another_required_soname(self):
        directory = self.toolchain / "misnamed"
        directory.mkdir()
        libc = self.toolchain / "lib/libc.so.6"
        libc.rename(directory / "libm.so.6")
        libc.symlink_to("../misnamed/libm.so.6")
        (self.toolchain / "lib/libm.so.6").unlink()
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required runtime library not found: libm.so.6", result.stderr)
        self.assertFalse(self.output.exists())

    def test_wrong_elf_architecture_is_rejected(self):
        library = self.toolchain / "lib/libc.so.6"
        contents = bytearray(library.read_bytes())
        contents[18:20] = (62).to_bytes(2, "little")
        library.write_bytes(contents)
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AArch64 ELF64", result.stderr)
        self.assertFalse(self.output.exists())

    def test_wrong_compiler_target_is_rejected(self):
        compiler = self.toolchain / "bin/gcc"
        compiler.write_text(compiler.read_text().replace("aarch64-linux-gnu", "x86_64-linux-gnu"))
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected aarch64-linux-gnu", result.stderr)
        self.assertFalse(self.output.exists())

    def test_wrong_gcc_major_is_rejected(self):
        compiler = self.toolchain / "bin/gcc"
        compiler.write_text(compiler.read_text().replace("13.3.0", "14.1.0"))
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected GCC 13", result.stderr)
        self.assertFalse(self.output.exists())

    def test_existing_file_and_symlink_are_never_overwritten(self):
        original = self.root / "original"
        original.write_bytes(b"preserve this existing artifact")
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                if symlink:
                    self.output.symlink_to(original)
                else:
                    self.output.write_bytes(original.read_bytes())
                result = self.export()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("output already exists", result.stderr)
                self.assertEqual(self.output.read_bytes(), b"preserve this existing artifact")
                self.assertEqual(self.output.is_symlink(), symlink)
                self.output.unlink()
        self.assertEqual(original.read_bytes(), b"preserve this existing artifact")

    def test_library_basename_collision_is_rejected(self):
        for index, name in enumerate(("libc.so.6", "libm.so.6")):
            directory = self.toolchain / "lib" / str(index)
            directory.mkdir()
            subprocess.run([self.compiler, "-shared", "-fPIC", "-nostdlib", "-Wl,-soname," + name,
                            str(self.toolchain / "source.c"), "-o", str(directory / "runtime.so")],
                           check=True, capture_output=True)
            alias = self.toolchain / "lib" / name
            alias.unlink()
            alias.symlink_to(str(index) + "/runtime.so")
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("library name collision: runtime.so", result.stderr)
        self.assertFalse(self.output.exists())

    def test_runtime_soname_must_match_the_requested_library(self):
        subprocess.run([self.compiler, "-shared", "-fPIC", "-nostdlib", "-Wl,-soname,libwrong.so.6",
                        str(self.toolchain / "source.c"), "-o", str(self.toolchain / "lib/libm.so.6")],
                       check=True, capture_output=True)
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime SONAME mismatch", result.stderr)
        self.assertFalse(self.output.exists())

    def test_compiler_library_environment_does_not_redirect_discovery(self):
        compiler = self.toolchain / "bin/gcc"
        compiler.write_text(compiler.read_text().replace("set -eu\n", "set -eu\n"
                            '[[ -z "${LIBRARY_PATH+x}${GCC_EXEC_PREFIX+x}${COMPILER_PATH+x}" ]] || exit 71\n'))
        environment = dict(os.environ, LIBRARY_PATH="/unreviewed", GCC_EXEC_PREFIX="/unreviewed/",
                           COMPILER_PATH="/unreviewed")
        result = self.export(env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tar_options_cannot_silently_exclude_required_libraries(self):
        result = self.export(env=dict(os.environ, TAR_OPTIONS="--exclude=libc.so.6"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tarfile.open(self.output) as archive:
            self.assertEqual(archive.extractfile("opt/eros/lib/libc.so.6").read(),
                             (self.toolchain / "lib/libc.so.6").read_bytes())


if __name__ == "__main__":
    unittest.main()
