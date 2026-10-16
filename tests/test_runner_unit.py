"""Runner contract tests; no Bazel server or network required."""

from pathlib import Path
from contextlib import redirect_stderr
import io
import os
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_runner import Case, Context, ROOT, execute, main as runner_main, report_data, select_cases


class RunnerTests(unittest.TestCase):
    def test_incomplete_full_suite_is_not_acceptance(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            result = execute(Case("TC-X-01", "pass", "P0", "local", lambda context: None),
                             Context(Path(temporary), "linux_arm64"))
            report = report_data([result], "linux_arm64", "test", True, 2)
            self.assertFalse(report["run_complete"])
            self.assertFalse(report["selected_scopes_passed"])
            self.assertFalse(report["acceptance_complete"])

    def test_cache_audit_detects_same_size_write_without_reading_payload(self):
        from acceptance_cases import user_conan_snapshot

        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            file = root / "package.a"
            file.write_bytes(b"old")
            original = file.stat()
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must not hash the cache")):
                before = user_conan_snapshot(root)
                file.write_bytes(b"new")
                os.utime(file, ns=(original.st_atime_ns, original.st_mtime_ns))
                after = user_conan_snapshot(root)
            self.assertNotEqual(before, after)

    def test_cache_audit_has_a_deadline(self):
        from acceptance_cases import user_conan_snapshot
        from test_runner import Blocked

        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            with self.assertRaises(Blocked):
                user_conan_snapshot(Path(temporary), timeout=0)

    def test_every_specification_case_is_registered(self):
        from acceptance_cases import CASES

        specification = (ROOT / "documents/test-design.md").read_text()
        expected = set(re.findall(r"\|\s*(TC-[A-Z]+-\d+)[^|\n]*P[01]", specification))
        actual = {case.id.split("/")[0] for case in CASES}
        self.assertEqual(len(expected), 50)
        self.assertEqual(actual, expected)
        self.assertEqual(len({case.id for case in CASES}), len(CASES))

    def test_filter_selects_all_scopes(self):
        cases = [Case("TC-ENV-01/local", "local", "P0", "local"),
                 Case("TC-ENV-01/target", "target", "P0", "target")]
        self.assertEqual(select_cases(cases, ["TC-ENV-01"]), cases)
        self.assertEqual(select_cases(cases, ["TC-ENV-01/local"]), cases[:1])

    def test_unknown_filter_is_error(self):
        with self.assertRaises(ValueError):
            select_cases([], ["TC-NOTHING-00"])

    def test_cross_elf_is_checked_against_its_branch_not_execution_cpu(self):
        from acceptance_cases import elf

        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            context = Context(Path(temporary), "linux_x86_64")
            with patch.object(context, "run", return_value=subprocess.CompletedProcess([], 0, "Machine: AArch64")):
                elf(context, Path("target"), "linux_x86_64_cross_arm64")
                with self.assertRaises(AssertionError):
                    elf(context, Path("target"))

    def test_existing_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            previous = Path(temporary) / "previous.log"
            previous.write_text("original evidence")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner_main(["--tc", "TC-SAN-05", "--evidence", temporary])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(previous.read_text(), "original evidence")

    def test_empty_results_are_not_acceptance(self):
        self.assertFalse(report_data([], "linux_arm64", "test")["acceptance_complete"])

    def test_partial_selection_is_not_full_acceptance(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            result = execute(Case("TC-X-01", "pass", "P0", "local", lambda context: None),
                             Context(Path(temporary), "linux_arm64"))
            report = report_data([result], "linux_arm64", "test")
            self.assertTrue(report["selected_scopes_passed"])
            self.assertFalse(report["acceptance_complete"])

    def test_blocked_never_becomes_pass(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            result = execute(Case("TC-X-01", "blocked", "P0", "E-RC", unavailable="No E-RC"),
                             Context(Path(temporary), "linux_arm64"))
            self.assertEqual(result.status, "BLOCKED")
            self.assertEqual(result.reason, "No E-RC")
            self.assertFalse(report_data([result], "linux_arm64", "test")["acceptance_complete"])

    def test_failure_has_evidence(self):
        def fail(context):
            raise ValueError("real failure")

        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            result = execute(Case("TC-X-02", "failure", "P0", "local", fail),
                             Context(Path(temporary), "linux_arm64"))
            self.assertEqual(result.status, "FAIL")
            self.assertTrue((Path(temporary) / "failure.txt").exists())

    def test_expected_nonzero_requires_real_exit(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            context = Context(Path(temporary), "linux_arm64")
            with self.assertRaises(AssertionError):
                context.run(["/bin/false"])
            result = context.run(["/bin/false"], expected=None)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(context.commands), 2)

    def test_missing_tool_has_exit_code_and_evidence(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            context = Context(Path(temporary), "linux_arm64")
            result = context.run(["/tmp/kilo/forge-nonexistent-tool"], expected=None)
            self.assertEqual(result.returncode, 127)
            self.assertEqual(context.commands[0]["exit_code"], 127)
            self.assertTrue((Path(temporary) / "001.log").is_file())


if __name__ == "__main__":
    unittest.main()
