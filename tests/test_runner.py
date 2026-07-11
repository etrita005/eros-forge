#!/usr/bin/env python3
"""
EROS Forge Test Runner

Features:
- Run all tests or specific tests / config types
- Filter tests by name substring (--filter)
- Parallel execution across test projects (--jobs); each project uses its own
  Bazel workspace, so cross-project parallelism is safe. Scripts within a single
  project run sequentially (they share one Bazel server / output base).
- Generate detailed test reports
"""

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# config_type -> test script basename
CONFIG_SCRIPTS = {
    "platform": "test_platform_configs.sh",
    "build_mode": "test_build_modes.sh",
    "sanitizer": "test_sanitizers.sh",
    "dependency": "test_dependency_consumption.sh",
    "deb": "test_deb_packaging.sh",
}

TEST_PROJECTS = ["bazel_simple", "bazel_cmake", "bazel_cmake_conan"]


class TestRunner:
    def __init__(self, jobs: int = 1, filt: Optional[str] = None):
        self.test_dir = Path(__file__).parent
        self.results: List[Dict] = []
        self.jobs = max(1, jobs)
        self.filt = filt
        self.start_time = None

    def _scripts_for(self, test_name: str, config_type: Optional[str]) -> List[tuple]:
        """Return [(script_path, display_name)] for the given project/config."""
        configs_dir = self.test_dir / test_name / "test_configs"
        if not configs_dir.exists():
            return []
        if config_type:
            script_name = CONFIG_SCRIPTS.get(config_type)
            if not script_name:
                return []
            script_path = configs_dir / script_name
            return [(script_path, "{}_{}".format(test_name, config_type))] if script_path.exists() else []
        out = []
        for cfg, script_name in CONFIG_SCRIPTS.items():
            script_path = configs_dir / script_name
            if script_path.exists():
                out.append((script_path, "{}_{}".format(test_name, cfg)))
        return out

    def _matches_filter(self, display_name: str) -> bool:
        if not self.filt:
            return True
        return self.filt.lower() in display_name.lower()

    def run_test_script(self, script_path: Path, test_name: str) -> Dict:
        """Run a single test script and return a result dict."""
        result = {
            "test_name": test_name,
            "script": str(script_path),
            "passed": False,
            "duration": 0,
            "output": "",
            "error": "",
        }
        start = time.time()
        print("\n" + "=" * 60)
        print("Running: {}".format(test_name))
        print("Script: {}".format(script_path))
        print("=" * 60)
        try:
            proc = subprocess.run(
                ["bash", str(script_path)],
                capture_output=True,
                text=True,
                timeout=3600,
                cwd=script_path.parent.parent.parent,
            )
            result["duration"] = time.time() - start
            result["output"] = proc.stdout
            result["error"] = proc.stderr
            result["passed"] = proc.returncode == 0
            if result["passed"]:
                print("\n\u2713 {} PASSED ({:.2f}s)\n".format(test_name, result["duration"]))
            else:
                print("\n\u2717 {} FAILED ({:.2f}s)\n".format(test_name, result["duration"]))
                if proc.stderr:
                    print("STDERR:", proc.stderr)
        except subprocess.TimeoutExpired:
            result["duration"] = time.time() - start
            result["error"] = "Test timed out after 3600 seconds"
            print("\n\u2717 {} TIMEOUT\n".format(test_name))
        except Exception as e:  # noqa: BLE001
            result["duration"] = time.time() - start
            result["error"] = str(e)
            print("\n\u2717 {} ERROR: {}\n".format(test_name, e))
        return result

    def _run_project(self, test_name: str, config_type: Optional[str]) -> List[Dict]:
        """Run all matching scripts for one project sequentially."""
        results = []
        for script_path, display_name in self._scripts_for(test_name, config_type):
            if not self._matches_filter(display_name):
                continue
            results.append(self.run_test_script(script_path, display_name))
        return results

    def run_test(self, test_name: str, config_type: Optional[str] = None):
        if not (self.test_dir / test_name).exists():
            print("Error: Test '{}' not found".format(test_name))
            return
        self.results.extend(self._run_project(test_name, config_type))

    def run_all_tests(self, config_type: Optional[str] = None):
        projects = [p for p in TEST_PROJECTS if (self.test_dir / p).exists()]
        if self.jobs == 1 or len(projects) <= 1:
            for test_name in projects:
                self.run_test(test_name, config_type)
            return
        # Cross-project parallelism (each project is an independent Bazel workspace).
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            futures = {
                pool.submit(self._run_project, test_name, config_type): test_name
                for test_name in projects
            }
            for fut in as_completed(futures):
                self.results.extend(fut.result())

    def generate_report(self, output_file: Optional[str] = None) -> bool:
        total_duration = sum(r["duration"] for r in self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = len(self.results) - passed
        report_lines = [
            "=" * 80,
            "EROS Forge Test Report",
            "=" * 80,
            "Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "Total Duration: {:.2f} seconds".format(total_duration),
            "Total Tests: {}".format(len(self.results)),
            "Passed: {}".format(passed),
            "Failed: {}".format(failed),
            "Success Rate: {:.1f}%".format((passed / len(self.results) * 100) if self.results else 0),
            "",
            "=" * 80,
            "Test Details",
            "=" * 80,
        ]
        for result in self.results:
            status = "\u2713 PASS" if result["passed"] else "\u2717 FAIL"
            report_lines.append("\n{} - {}".format(status, result["test_name"]))
            report_lines.append("  Duration: {:.2f}s".format(result["duration"]))
            report_lines.append("  Script: {}".format(result["script"]))
            if not result["passed"] and result["error"]:
                report_lines.append("  Error: {}".format(result["error"]))
        report_lines.append("\n" + "=" * 80)
        report = "\n".join(report_lines)
        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            print("\nReport saved to: {}".format(output_file))
        print(report)
        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="EROS Forge Test Runner")
    parser.add_argument("--test", help="Run specific test (bazel_simple, bazel_cmake, bazel_cmake_conan)")
    parser.add_argument(
        "--config",
        help="Run specific config type ({})".format(", ".join(CONFIG_SCRIPTS)),
    )
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--report", help="Generate report to file")
    parser.add_argument(
        "--filter",
        help="Only run tests whose name contains this substring (e.g. 'platform', 'asan')",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Run test projects in parallel (each is a separate Bazel workspace). Default: 1",
    )
    args = parser.parse_args()

    runner = TestRunner(jobs=args.jobs, filt=args.filter)
    runner.start_time = time.time()

    if args.all:
        runner.run_all_tests(args.config)
    elif args.test:
        runner.run_test(args.test, args.config)
    else:
        parser.print_help()
        sys.exit(1)

    success = runner.generate_report(args.report)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
