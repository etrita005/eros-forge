#!/usr/bin/env python3
"""
EROS Forge Test Runner

Features:
- Run all tests or specific tests
- Support for specific configuration runs
- Generate detailed test reports
- Support for parallel testing
- Support for test result summary
"""

import argparse
import subprocess
import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

class TestRunner:
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.results = []
        self.start_time = None
        
    def run_test_script(self, script_path: Path, test_name: str) -> Dict:
        """
        Run a single test script
        
        Args:
            script_path: Path to the test script
            test_name: Name of the test
        
        Returns:
            Test result dictionary
        """
        result = {
            "test_name": test_name,
            "script": str(script_path),
            "passed": False,
            "duration": 0,
            "output": "",
            "error": ""
        }
        
        start = time.time()
        
        try:
            print(f"\n{'='*60}")
            print(f"Running: {test_name}")
            print(f"Script: {script_path}")
            print(f"{'='*60}\n")
            
            proc = subprocess.run(
                ["bash", str(script_path)],
                capture_output=True,
                text=True,
                timeout=3600,
                cwd=script_path.parent.parent
            )
            
            result["duration"] = time.time() - start
            result["output"] = proc.stdout
            result["error"] = proc.stderr
            result["passed"] = proc.returncode == 0
            
            if result["passed"]:
                print(f"\n✓ {test_name} PASSED ({result['duration']:.2f}s)\n")
            else:
                print(f"\n✗ {test_name} FAILED ({result['duration']:.2f}s)\n")
                if proc.stderr:
                    print("STDERR:", proc.stderr)
                    
        except subprocess.TimeoutExpired:
            result["duration"] = time.time() - start
            result["error"] = "Test timed out after 3600 seconds"
            print(f"\n✗ {test_name} TIMEOUT\n")
        except Exception as e:
            result["duration"] = time.time() - start
            result["error"] = str(e)
            print(f"\n✗ {test_name} ERROR: {e}\n")
        
        return result
    
    def run_test(self, test_name: str, config_type: str = None):
        """
        Run specified test
        
        Args:
            test_name: Test name (bazel_simple, bazel_cmake, bazel_cmake_conan)
            config_type: Configuration type (platform, build_mode, sanitizer)
        """
        test_path = self.test_dir / test_name
        if not test_path.exists():
            print(f"Error: Test '{test_name}' not found")
            return
        
        test_configs_dir = test_path / "test_configs"
        if not test_configs_dir.exists():
            print(f"Error: test_configs directory not found for {test_name}")
            return
        
        if config_type:
            # Map configuration type to script name
            config_script_map = {
                "platform": "test_platform_configs.sh",
                "build_mode": "test_build_modes.sh",
                "sanitizer": "test_sanitizers.sh",
                "dependency": "test_dependency_consumption.sh"
            }
            script_name = config_script_map.get(config_type)
            if not script_name:
                print(f"Error: Unknown config type '{config_type}'")
                print(f"Valid options: platform, build_mode, sanitizer, dependency")
                return
            
            script_path = test_configs_dir / script_name
            if not script_path.exists():
                print(f"Error: Test script '{script_name}' not found")
                return
            
            result = self.run_test_script(script_path, f"{test_name}_{config_type}")
            self.results.append(result)
        else:
            scripts = [
                ("test_platform_configs.sh", "platform"),
                ("test_build_modes.sh", "build_mode"),
                ("test_sanitizers.sh", "sanitizer"),
                ("test_dependency_consumption.sh", "dependency")
            ]
            
            for script_name, config in scripts:
                script_path = test_configs_dir / script_name
                if script_path.exists():
                    result = self.run_test_script(script_path, f"{test_name}_{config}")
                    self.results.append(result)
    
    def run_all_tests(self, config_type: str = None):
        """
        Run all tests
        
        Args:
            config_type: Configuration type (platform, build_mode, sanitizer)
        """
        test_projects = ["bazel_simple", "bazel_cmake", "bazel_cmake_conan"]
        
        for test_name in test_projects:
            test_path = self.test_dir / test_name
            if test_path.exists():
                self.run_test(test_name, config_type)
    
    def generate_report(self, output_file: str = None):
        """
        Generate test report
        
        Args:
            output_file: Output file path (optional)
        """
        total_duration = sum(r["duration"] for r in self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = len(self.results) - passed
        
        report_lines = [
            "=" * 80,
            "EROS Forge Test Report",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Duration: {total_duration:.2f} seconds",
            f"Total Tests: {len(self.results)}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Success Rate: {(passed/len(self.results)*100) if self.results else 0:.1f}%",
            "",
            "=" * 80,
            "Test Details",
            "=" * 80,
        ]
        
        for result in self.results:
            status = "✓ PASS" if result["passed"] else "✗ FAIL"
            report_lines.append(f"\n{status} - {result['test_name']}")
            report_lines.append(f"  Duration: {result['duration']:.2f}s")
            report_lines.append(f"  Script: {result['script']}")
            
            if not result["passed"] and result["error"]:
                report_lines.append(f"  Error: {result['error']}")
        
        report_lines.append("\n" + "=" * 80)
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            print(f"\nReport saved to: {output_file}")
        
        print(report)
        
        return failed == 0

def main():
    parser = argparse.ArgumentParser(description="EROS Forge Test Runner")
    parser.add_argument("--test", help="Run specific test (bazel_simple, bazel_cmake, bazel_cmake_conan)")
    parser.add_argument("--config", help="Run specific config type (platform, build_mode, sanitizer, dependency)")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--report", help="Generate report to file")
    
    args = parser.parse_args()
    
    runner = TestRunner()
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
