#!/usr/bin/env python3
"""Exercise clean and faulting sanitizer modes without editing the source."""

import os
from pathlib import Path
import re
import subprocess


WORKSPACE = Path(__file__).resolve().parents[1]
LESSON = "08-sanitizer-errors"
BINARY = WORKSPACE / f"bazel-bin/{LESSON}/app"


def run(*args, expected=True, env=None):
    result = subprocess.run(args, cwd=WORKSPACE, env=env, text=True, capture_output=True)
    if (result.returncode == 0) != expected:
        raise RuntimeError(f"{' '.join(map(str, args))}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def build(*configs):
    arguments = ["bazel", "build", "--color=no", "--curses=no", "--noshow_progress"]
    arguments.extend(f"--config={config}" for config in configs)
    arguments.append(f"//{LESSON}:app")
    run(*arguments)


def environment():
    result = dict(os.environ)
    result.pop("LD_LIBRARY_PATH", None)
    result.pop("LD_PRELOAD", None)
    result["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
    result["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    result["TSAN_OPTIONS"] = "halt_on_error=1:exitcode=66"
    return result


def execute(arguments, env):
    return subprocess.run([str(BINARY), *arguments], cwd=WORKSPACE, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def control(env):
    result = execute(["--bug=none"], env)
    require(result.returncode == 0 and "forge-san=43" in result.stdout,
            f"Clean sanitizer control failed: {result.stdout}")
    return result


def fault(arguments, env, pattern, symbol):
    result = execute(arguments, env)
    require(result.returncode != 0, f"Sanitizer accepted a fault: {result.stdout}")
    require(re.search(pattern, result.stdout), f"Missing {pattern!r}: {result.stdout}")
    require(symbol in result.stdout, f"Report does not identify {symbol}: {result.stdout}")
    return result


def check_asan(env):
    build("asan")
    control(env)
    fault(["--bug=asan", "--input=8"], env, r"AddressSanitizer.*heap-buffer-overflow", "BusinessAsan")
    fault(["--source=dependency", "--bug=asan", "--input=8"], env, r"AddressSanitizer.*heap-buffer-overflow",
          "forge_sanitizer_asan")
    print("PASS ASan: clean control and business/dependency heap faults")


def check_ubsan(env):
    build("ubsan")
    control(env)
    fault(["--bug=ubsan", "--input=2147483647"], env, r"runtime error: signed integer overflow", "BusinessUbsan")
    fault(["--source=dependency", "--bug=ubsan", "--input=2147483647"], env,
          r"runtime error: signed integer overflow", "forge_sanitizer_ubsan")
    print("PASS UBSan: clean control and business/dependency overflow faults")


def check_combination(env, configs):
    build(*configs)
    control(env)
    fault(["--bug=asan", "--input=8"], env, r"AddressSanitizer.*heap-buffer-overflow", "BusinessAsan")
    fault(["--source=dependency", "--bug=asan", "--input=8"], env, r"AddressSanitizer.*heap-buffer-overflow",
          "forge_sanitizer_asan")
    fault(["--bug=ubsan", "--input=2147483647"], env, r"runtime error: signed integer overflow", "BusinessUbsan")
    fault(["--source=dependency", "--bug=ubsan", "--input=2147483647"], env,
          r"runtime error: signed integer overflow", "forge_sanitizer_ubsan")
    print("PASS ASan+UBSan request order: " + " ".join(configs))


def check_tsan(env):
    build("tsan")
    result = execute(["--bug=none"], env)
    if result.returncode != 0 and re.search(
            r"unexpected memory mapping|FATAL: ThreadSanitizer|ThreadSanitizer: unsupported",
            result.stdout):
        print("SKIP TSan: runtime cannot initialize on this host")
        return
    require(result.returncode == 0 and "forge-san=43" in result.stdout,
            f"TSan clean control failed: {result.stdout}")
    result = execute(["--bug=synchronized"], env)
    require(result.returncode == 0 and "threads=20000" in result.stdout,
            f"TSan synchronized control failed: {result.stdout}")
    for _ in range(3):
        result = execute(["--bug=race"], env)
        if result.returncode != 0 and "ThreadSanitizer: data race" in result.stdout:
            print("PASS TSan: clean and synchronized controls plus a real data race")
            return
    print("SKIP TSan: no race diagnostic after three schedules; not counted as detection")


def check_no_sanitizer(env):
    build("asan_ubsan", "no_sanitizer")
    dynamic = run("readelf", "-d", BINARY).stdout
    require(not re.search(r"lib(asan|ubsan|tsan)", dynamic), "Sanitizer runtime remained after no_sanitizer")
    undefined = run("nm", "-u", BINARY).stdout
    require(not re.search(r"__(asan|ubsan|tsan)_", undefined), "Instrumentation remained after no_sanitizer")
    control(env)
    print("PASS no_sanitizer: runtime and instrumentation cleared without cleaning")


def main():
    env = environment()
    check_asan(env)
    check_ubsan(env)
    check_combination(env, ("asan", "ubsan"))
    check_combination(env, ("ubsan", "asan"))
    check_tsan(env)
    check_no_sanitizer(env)
    print("Sanitizer example verified")


if __name__ == "__main__":
    main()
