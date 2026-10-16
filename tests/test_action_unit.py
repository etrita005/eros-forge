"""Architecture-specific symbols, including mixed Conan host/build contexts."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_runner import ROOT


SPEC = importlib.util.spec_from_file_location("forge_action_common", ROOT / "bazel/tools/action_common.py")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)


class ActionToolsTests(unittest.TestCase):
    def test_split_dwarf_is_not_complete_independent_debug_info(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            source = root / "source.c"
            source.write_text("int forge_skeleton(void) { return 42; }\n")
            binary = root / "skeleton.so"
            subprocess.run(["gcc-13", "-g", "-gsplit-dwarf", "-fPIC", "-shared", "-nostdlib", source, "-o", binary],
                           check=True, capture_output=True)
            self.assertTrue(list(root.rglob("*.dwo")))
            tools = {tool: {"path": shutil.which(tool)} for tool in ("objdump", "readelf")}
            self.assertFalse(common.has_debug(binary, tools, os.environ.copy()))

    def test_mixed_target_and_build_contexts_use_matching_binutils(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            source = root / "source.c"
            source.write_text("int forge_debug_architecture(void) { return 42; }\n")
            packages = root / "packages"
            tools = {}
            for name, prefix in (("native", "x86_64-linux-gnu-"), ("cross_arm64", "aarch64-linux-gnu-")):
                compiler = shutil.which(prefix + "gcc")
                if not compiler:
                    self.skipTest("This focused binutils test requires both installed cross-target GCC drivers")
                tools[name] = {tool: {"path": shutil.which(prefix + tool)} for tool in ("objcopy", "objdump", "strip", "readelf")}
                self.assertTrue(all(record["path"] for record in tools[name].values()))
                package = packages / ("build_tool" if name == "native" else "target")
                package.mkdir(parents=True)
                subprocess.run([compiler, "-g", "-fPIC", "-shared", "-nostdlib", "-Wl,--build-id",
                                source, "-o", package / "library.so"], check=True, capture_output=True)
            manifest = {"tools": tools["native"], "toolchains": {key: {"tools": value} for key, value in tools.items()}}
            selected = common.target_tools(manifest, "linux_x86_64_cross_arm64")
            self.assertEqual(selected["objcopy"], tools["cross_arm64"]["objcopy"])
            binaries = common.debug_artifacts(packages, root / "symbols", root / "identity.json", selected,
                                              os.environ.copy(), True, {"preset": "linux_x86_64_cross_arm64"},
                                              strip=False, tools_by_directory={"build_tool": tools["native"]})
            self.assertEqual(len(binaries), 2)
            machines = {int.from_bytes((root / pair["debug_file"]).read_bytes()[18:20], "little") for pair in binaries}
            self.assertEqual(machines, {62, 183})


if __name__ == "__main__":
    unittest.main()
