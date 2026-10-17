#!/usr/bin/env python3
"""Build/run the native introductory lessons, reusing this workspace's output base."""

import argparse
from datetime import datetime, timezone
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


ROOT = Path(__file__).resolve().parent
LESSONS = ("01-minimal-app", "02-native-library", "03-cmake-library", "04-conan-locked")


def source_snapshot():
    paths = [ROOT / "MODULE.bazel", ROOT / "MODULE.bazel.lock", ROOT / ".bazelrc", ROOT / "check.py"]
    for directory in (*LESSONS, "_support"):
        paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def cache_snapshot():
    home = Path.home() / ".conan2"
    if not home.exists():
        return {"<home>": "absent"}
    deadline = time.monotonic() + 30
    result = {}
    for path in chain((home,), home.rglob("*")):
        if time.monotonic() > deadline:
            raise RuntimeError("Conan cache metadata audit exceeded 30s; cache payloads were not read")
        state = path.lstat()
        result[str(path.relative_to(home))] = (state.st_mode, state.st_size, state.st_mtime_ns,
                                             state.st_ctime_ns, os.readlink(path) if path.is_symlink() else "")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("debug", "release"), action="append")
    parser.add_argument("--report", type=Path, default=ROOT / ".forge-evidence/check.json")
    args = parser.parse_args()
    modes = list(dict.fromkeys(args.mode or ("debug", "release")))
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    logs = report.parent / (report.stem + "-logs-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    logs.mkdir()
    data = {"status": "RUNNING", "modes": modes, "commands": [], "runs": [], "snapshots": []}

    def save():
        report.write_text(json.dumps(data, indent=2) + "\n")

    def run(arguments):
        command = ["bazel", *arguments]
        print("RUN " + shlex.join(command), flush=True)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", LC_ALL="C")
        environment.pop("LD_LIBRARY_PATH", None)
        started = time.monotonic()
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True,
                                    timeout=300, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Bazel command exceeded 300s: " + shlex.join(command)) from None
        logfile = logs / f"{len(data['commands']) + 1:03d}.log"
        logfile.write_text("$ " + shlex.join(command) + "\n" + result.stdout + result.stderr)
        data["commands"].append({"argv": command, "exit_code": result.returncode,
                                 "seconds": round(time.monotonic() - started, 3), "log": str(logfile)})
        save()
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}); see {logfile}")
        return result.stdout.strip()

    save()
    try:
        print("Auditing declared source inputs and user Conan cache metadata", flush=True)
        before_source, before_cache = source_snapshot(), cache_snapshot()
        lock_digest = before_source["04-conan-locked/conan.lock"]
        execution_root = Path(run(["info", "execution_root"]))
        data["output_base"] = run(["info", "output_base"])
        for mode in modes:
            options = [f"--config={mode}", "--color=no", "--curses=no", "--noshow_progress"]
            run(["build", *options, *[f"//{lesson}:app" for lesson in LESSONS]])
            for lesson in LESSONS:
                target = f"//{lesson}:app"
                output = run(["run", *options, target])
                if output != "result=41":
                    raise RuntimeError(f"{mode} {target}: expected result=41, got {output!r}")
                data["runs"].append({"mode": mode, "target": target, "output": output, "status": "PASS"})
                save()
                print(f"PASS {mode} {target}: {output}", flush=True)
            target = "//04-conan-locked:answer_conan"
            output = run(["cquery", *options, f"config({target}, target)", f"--universe_scope={target}", "--output=files"])
            paths = [execution_root / line for line in output.splitlines() if line.endswith(".manifest.json")]
            if len(paths) != 1:
                raise RuntimeError("Expected one declared Conan identity manifest")
            snapshot = json.loads(paths[0].read_text())
            if not snapshot["private_home_removed"] or snapshot["variant"]["lock_sha256"] != lock_digest:
                raise RuntimeError("Snapshot must use the reviewed lock and remove its private home")
            packages = snapshot["packages"]
            expected_type = "Debug" if mode == "debug" else "Release"
            if len(packages) != 1 or not packages[0]["ref"].startswith("tiny_math/1.0#"):
                raise RuntimeError("Unexpected dependency graph")
            if packages[0]["binary"] != "Build" or packages[0]["settings"]["build_type"] != expected_type:
                raise RuntimeError("Source-only index did not produce the expected dependency variant")
            data["snapshots"].append({"mode": mode, "manifest": str(paths[0]), "package": packages[0],
                                      "environment_sha256": snapshot["variant"]["environment_sha256"]})
        if source_snapshot() != before_source:
            raise RuntimeError("Builds modified example source inputs or the reviewed Conan lock")
        print("Auditing user Conan cache metadata after builds", flush=True)
        if cache_snapshot() != before_cache:
            raise RuntimeError("User Conan cache metadata changed during example verification")
        data.update(status="PASS", source_inputs_unchanged=True, user_cache_metadata_unchanged=True,
                    conan_lock_sha256=lock_digest, module_lock_sha256=before_source["MODULE.bazel.lock"])
        print(f"PASS {len(data['runs'])} native runs; source/lock/cache audits passed. Report: {report}", flush=True)
        return 0
    except (OSError, RuntimeError, KeyError, ValueError) as error:
        data.update(status="FAIL", error=str(error))
        print("FAIL " + str(error), flush=True)
        return 1
    finally:
        save()


if __name__ == "__main__":
    raise SystemExit(main())
