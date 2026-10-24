"""Runner contract tests; no Bazel server or network required."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.conan import verify as conan_verify
from test_runner import Case, Context, ROOT, execute, main as runner_main, report_data, select_cases


class RunnerTests(unittest.TestCase):
    def test_local_image_provenance_failure_never_reports_pass(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            report = root / "report.json"
            with patch("test_runner.capture_provenance", return_value={
                "local_image_id_claim": "sha256:claimed",
                "environment_capture_error": "baseline mismatch",
            }), patch.object(Context, "run", return_value=subprocess.CompletedProcess([], 0, "")), \
                 redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                result = runner_main(["--tc", "TC-ENV-02/local", "--preset", "linux_x86_64",
                                      "--evidence", str(root / "evidence"), "--report", str(report), "--strict"])
            data = json.loads(report.read_text())
            self.assertEqual(result, 1)
            self.assertFalse(data["selected_scopes_passed"])
            self.assertFalse(data["acceptance_complete"])
            self.assertEqual(data["provenance_status"], "FAIL")
            self.assertEqual(data["results"], [])
            self.assertIn("baseline mismatch", data["input_provenance"]["environment_capture_error"])

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

    def test_specification_cases_are_registered_or_explicitly_pending(self):
        from acceptance_cases import CASES

        specification = (ROOT / "documents/test-design.md").read_text()
        expected = set(re.findall(r"\|\s*(TC-[A-Z]+-\d+)[^|\n]*P[01]", specification))
        actual = {case.id.split("/")[0] for case in CASES}
        self.assertEqual(expected - actual, {
            "TC-ENV-05", "TC-ENV-06", "TC-ENV-07", "TC-ENTRY-01", "TC-ENTRY-02",
            "TC-ENTRY-03", "TC-ENTRY-04", "TC-ENTRY-05", "TC-CI-03",
        })
        self.assertFalse(actual - expected)
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

    def test_conan_scenario_forwards_runner_bazel_startup(self):
        from acceptance_cases import conan_scenario

        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            context = Context(root / "case", "linux_x86_64", output_base=root / "bazel-output-base")
            with patch.object(context, "run", return_value=subprocess.CompletedProcess([], 0, "PASS")) as run:
                conan_scenario(context, "TC-DEP-05")
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [sys.executable, "tests/fixtures/conan/verify.py", "--tc", "TC-DEP-05"])
            self.assertEqual(command[4:8], ["--evidence", context.evidence / "conan", "--preset", context.preset])
            self.assertEqual(command[8:],
                             [f"--bazel-startup={option}" for option in context.startup[1:]])
            self.assertEqual(run.call_args.kwargs, {"expected": None, "timeout": 1200})

    def test_conan_verifier_uses_explicit_base_for_every_bazel_command(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            base = root / "selected-base"
            execution_root = base / "execroot/_main"
            manifest = execution_root / "env_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"tools": {"python": {"path": "/usr/bin/python3"},
                                                     "conan": {"path": "/conan.py"}}}))
            context = Context(root / "case", "linux_x86_64", output_base=base)
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                output = (str(base) if command[-2:] == ["info", "output_base"] else
                          str(execution_root) if command[-2:] == ["info", "execution_root"] else
                          "env_manifest.json\n" if command[-1] == "--output=files" else "")
                return subprocess.CompletedProcess(command, 0, output, "")

            with patch.object(conan_verify.subprocess, "run", side_effect=run):
                checks = conan_verify.Checks(SimpleNamespace(evidence=root / "conan", bazel_startup=context.startup[1:]))
                checks.command(checks.bazel + ["build", "//tests/fixtures/fail:missing_lock_entry"])
            self.assertEqual(checks.output_base, base)
            self.assertEqual(commands, [context.startup + ["info", "output_base"],
                                        context.startup + ["info", "execution_root"],
                                        context.startup + ["cquery", "@eros_host_tools//:env_manifest", "--output=files"],
                                        context.startup + ["build", "//tests/fixtures/fail:missing_lock_entry"]])

    def test_conan_verifier_rejects_bazel_output_base_mismatch(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            root = Path(temporary)
            base = root / "selected-base"
            context = Context(root / "case", "linux_x86_64", output_base=base)
            with patch.object(conan_verify.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], 0, str(root / "wrong-base"), "")) as run:
                with self.assertRaisesRegex(AssertionError, "Bazel output_base mismatch"):
                    conan_verify.Checks(SimpleNamespace(evidence=root / "conan", bazel_startup=context.startup[1:]))
            self.assertEqual(run.call_args.args[0], context.startup + ["info", "output_base"])
            self.assertEqual(run.call_count, 1)

    def test_conan_verifier_direct_run_defaults_to_evidence_base(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            evidence = Path(temporary) / "conan"
            base = evidence / "bazel-output-base"
            execution_root = base / "execroot/_main"
            manifest = execution_root / "env_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"tools": {"python": {"path": "/usr/bin/python3"},
                                                     "conan": {"path": "/conan.py"}}}))

            def run_command(command, **kwargs):
                output = (str(base) if command[-2:] == ["info", "output_base"] else
                          str(execution_root) if command[-2:] == ["info", "execution_root"] else
                          "env_manifest.json\n")
                return subprocess.CompletedProcess(command, 0, output, "")

            with patch.object(conan_verify.subprocess, "run", side_effect=run_command) as run:
                checks = conan_verify.Checks(SimpleNamespace(evidence=evidence, bazel_startup=[]))
            self.assertEqual(checks.output_base, base)
            self.assertEqual(run.call_args_list[0].args[0],
                             ["bazel", "--bazelrc=bazel/bazelrc", f"--output_base={base}", "info", "output_base"])
            self.assertTrue(all(f"--output_base={base}" in call.args[0][:4] for call in run.call_args_list))

    def test_conan_verifier_requires_one_explicit_base_when_startup_is_passed(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as temporary:
            evidence = Path(temporary) / "conan"
            with patch.object(conan_verify.subprocess, "run") as run:
                for startup in (["--bazelrc=bazel/bazelrc"], ["--output_base=/tmp/one", "--output_base=/tmp/two"]):
                    with self.assertRaisesRegex(ValueError, "exactly one absolute --output_base"):
                        conan_verify.Checks(SimpleNamespace(evidence=evidence, bazel_startup=startup))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
