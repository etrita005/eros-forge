"""Debug source archives must not become undeclared producer build caches."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

from test_runner import ROOT


SPEC = importlib.util.spec_from_file_location("forge_snapshot_deployer", ROOT / "bazel/tools/snapshot_deployer.py")
deployer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployer)


class SourceSnapshotTests(unittest.TestCase):
    def test_patched_sources_and_generated_headers_only(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            source = root / "source"
            build = source / "build/Release"
            generators = build / "generators"
            generators.mkdir(parents=True)
            (build / "CMakeFiles/CompilerIdCXX").mkdir(parents=True)
            (source / "bar.cc").write_text("int patched_bias = 2;\n")
            (source / "CMakeLists.txt").write_text("project(bar)\n")
            (source / "bar_config.h.in").write_text("#define BIAS @BIAS@\n")
            (source / "fix.patch").write_text("patch content\n")
            (build / "generated.h").write_text("#define BIAS 2\n")
            (build / "CMakeFiles/CompilerIdCXX/compiler.cpp").write_text("compiler probe\n")
            (build / "CMakeCache.txt").write_text("/private/conan_home/build\n")
            (build / "Makefile").write_text("/private/conan_home/build\n")
            (build / "bar.o").write_bytes(b"object")
            (build / "libbar.a").write_bytes(b"!<arch>\narchive")
            (build / "extensionless_binary").write_bytes(b"\x7fELFbinary")
            (generators / "conan_toolchain.cmake").write_text("/private/conan_home/build\n")
            (source / "conanbuildenv-release.sh").write_text("/private/conan_home/build\n")
            (source / "CMakeUserPresets.json").write_text('{"include": "/private/conan_home/presets"}\n')
            destination = root / "snapshot"
            deployer.capture_sources(source, destination, build, generators)
            actual = {str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()}
            self.assertEqual(actual, {"bar.cc", "CMakeLists.txt", "bar_config.h.in", "fix.patch", "build/Release/generated.h"})
            self.assertIn("patched_bias = 2", (destination / "bar.cc").read_text())

    def test_source_link_cannot_escape_to_producer_home(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (root / "private.h").write_text("private producer state\n")
            (source / "escape.h").symlink_to("../private.h")
            with self.assertRaisesRegex(ValueError, "escapes"):
                deployer.capture_sources(source, root / "snapshot")


if __name__ == "__main__":
    unittest.main()
