#!/usr/bin/env python3
"""Case-level Forge acceptance runner. A blocked check is never a pass."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import time
import traceback
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
STATES = ("PASS", "FAIL", "SKIP", "BLOCKED")


class Blocked(Exception):
    """A documented environment prerequisite is unavailable."""


class Skipped(Exception):
    """This check does not apply to the selected execution platform."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    priority: str
    scope: str
    check: Callable[["Context"], None] | None = None
    unavailable: str = ""


@dataclass
class Result:
    id: str
    title: str
    priority: str
    scope: str
    status: str
    reason: str
    evidence: str
    duration_seconds: float
    commands: list[dict] = field(default_factory=list)


class Context:
    def __init__(self, evidence: Path, preset: str, jobs: int = 2, gdb: str = "gdb", output_base: Path | None = None):
        self.root = ROOT
        self.evidence = evidence
        self.preset = preset
        self.cross_preset = (
            "linux_arm64_cross_arm64" if platform.machine() in ("aarch64", "arm64")
            else "linux_x86_64_cross_arm64"
        )
        self.jobs = jobs
        self.gdb = gdb
        self.output_base = output_base
        self.execution_root = output_base / "execroot/_main" if output_base else self.root
        self.startup = ["bazel", f"--bazelrc={self.root / 'bazel/bazelrc'}"]
        if output_base:
            self.startup += [f"--output_base={output_base}", "--host_jvm_args=-Xmx1024m", "--max_idle_secs=60"]
        self.commands: list[dict] = []
        self.notes: list[str] = []
        self.evidence.mkdir(parents=True, exist_ok=True)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def run(
        self,
        command: list[str | Path],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        expected: int | None = 0,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(value) for value in command]
        environment = os.environ.copy()
        for name in ("LD_LIBRARY_PATH", "CONAN_HOME", "DEB_VERSION"):
            environment.pop(name, None)
        environment.update({"LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONOPTIMIZE": "0"})
        environment.update(env or {})
        index = len(self.commands) + 1
        logfile = self.evidence / f"{index:03d}.log"
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd or self.root,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or ""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            completed = subprocess.CompletedProcess(command, 124, output + "\nTIMEOUT\n")
        except OSError as error:
            completed = subprocess.CompletedProcess(command, 127, f"{type(error).__name__}: {error}\n")
        elapsed = round(time.monotonic() - started, 3)
        logfile.write_text(
            f"$ {shlex.join(command)}\n"
            f"cwd: {cwd or self.root}\nexit: {completed.returncode}\n"
            f"duration: {elapsed}s\n\n{completed.stdout}",
            encoding="utf-8",
        )
        self.commands.append({
            "argv": command,
            "cwd": str(cwd or self.root),
            "environment_overrides": env or {},
            "exit_code": completed.returncode,
            "duration_seconds": elapsed,
            "log": str(logfile),
        })
        if expected is not None:
            require(
                completed.returncode == expected,
                f"Expected exit {expected}, got {completed.returncode}: "
                f"{shlex.join(command)}; evidence {logfile}\n{completed.stdout[-8000:]}",
            )
        return completed

    def bazel(
        self,
        verb: str,
        targets: str | list[str],
        *,
        preset: str | None = None,
        mode: str = "debug",
        configs: tuple[str, ...] = (),
        flags: tuple[str, ...] | list[str] = (),
        expected: int | None = 0,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(targets, str):
            targets = [targets]
        command = self.startup + [
            verb,
            "--color=no", "--curses=no", "--noshow_progress", "--noshow_loading_progress",
            f"--config={preset or self.preset}", f"--config={mode}",
        ]
        command.extend(f"--config={config}" for config in configs)
        if verb in ("build", "test", "run"):
            command.append(f"--jobs={self.jobs}")
        command.extend(flags)
        command.extend(targets)
        return self.run(command, expected=expected, env=env, timeout=1200)

    def build(self, targets: str | list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        return self.bazel("build", targets, **kwargs)

    def files(self, target: str, **kwargs) -> list[Path]:
        result = self.bazel("cquery", f"config({target}, target)", flags=[
            "--output=files", f"--universe_scope={target}", *kwargs.pop("flags", ()),
        ], **kwargs)
        files = []
        # Bazel sends analysis diagnostics to stderr, merged by run(). Only
        # real output paths are accepted, never a success-looking log line.
        for line in result.stdout.splitlines():
            candidate = Path(line.strip())
            if not candidate.is_absolute():
                candidate = self.execution_root / candidate
            if candidate.exists() and candidate != self.execution_root:
                files.append(candidate)
        require(files, f"No existing declared outputs found for {target}")
        return files

    def output(self, target: str, suffix: str = "", **kwargs) -> Path:
        files = self.files(target, **kwargs)
        selected = [path for path in files if not suffix or path.name.endswith(suffix)]
        require(len(selected) == 1, f"Expected one {suffix!r} output for {target}, found {selected}")
        return selected[0]

    def negative(self, target: str, pattern: str, **kwargs) -> str:
        result = self.build(target, expected=None, **kwargs)
        require(result.returncode != 0, f"Invalid target unexpectedly built: {target}")
        require(re.search(pattern, result.stdout, re.IGNORECASE),
                f"Failure for {target} did not identify {pattern!r}:\n{result.stdout}")
        return result.stdout


def select_cases(cases: list[Case], requested: list[str]) -> list[Case]:
    if not requested:
        return cases
    chosen = []
    for case in cases:
        if any(case.id == value or case.id.startswith(value + "/") for value in requested):
            chosen.append(case)
    unknown = [value for value in requested if not any(
        case.id == value or case.id.startswith(value + "/") for case in cases
    )]
    if unknown:
        raise ValueError(f"Unknown test case(s): {', '.join(unknown)}")
    return chosen


def execute(case: Case, context: Context) -> Result:
    started = time.monotonic()
    status = "PASS"
    reason = ""
    try:
        if case.unavailable:
            raise Blocked(case.unavailable)
        require(case.check is not None, f"No implementation registered for {case.id}")
        case.check(context)
        reason = "\n".join(context.notes) or "Assertions passed for the stated scope."
    except Blocked as error:
        status, reason = "BLOCKED", str(error)
    except Skipped as error:
        status, reason = "SKIP", str(error)
    except Exception as error:
        status, reason = "FAIL", f"{type(error).__name__}: {error}"
        (context.evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    result = Result(
        case.id, case.title, case.priority, case.scope, status, reason,
        str(context.evidence), round(time.monotonic() - started, 3), context.commands,
    )
    (context.evidence / "result.json").write_text(json.dumps(asdict(result), indent=2) + "\n")
    return result


def report_data(results: list[Result], preset: str, source_revision: str, full_suite: bool = False, expected_scopes: int | None = None) -> dict:
    counts = {state: sum(result.status == state for result in results) for state in STATES}
    expected_scopes = len(results) if expected_scopes is None else expected_scopes
    complete = len(results) == expected_scopes
    return {
        "schema_version": 1,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
        "source_state": "working tree; see command evidence and file digests",
        "execution_environment": {"os": platform.platform(), "cpu": platform.machine()},
        "preset": preset,
        "counts": counts,
        "expected_scope_count": expected_scopes,
        "run_complete": complete,
        "full_suite_selected": full_suite,
        "selected_scopes_passed": complete and bool(results) and counts["PASS"] == len(results),
        "acceptance_complete": complete and full_suite and bool(results) and counts["PASS"] == len(results),
        "scope_notice": "Local checks do not replace E-X2/E-RC/E-TA acceptance. Read each scope.",
        "results": [asdict(result) for result in results],
    }


def capture_provenance(evidence: Path, preset: str, jobs: int, output_base: Path, gdb: str) -> dict:
    context = Context(evidence / "inputs", preset, jobs, output_base=output_base)
    source_files = context.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
    entries = {}
    for value in source_files.stdout.splitlines():
        path = ROOT / value
        if path.is_file():
            entries[value] = digest(path)
    source_manifest = context.evidence / "source_manifest.json"
    source_manifest.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    context.run(["git", "status", "--short"])
    context.run(["git", "diff", "--no-ext-diff", "--binary"])
    provenance = {
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": digest(source_manifest),
        "locks": {name: sha for name, sha in entries.items() if name.endswith(".lock")},
        "bazel_output_base": str(output_base),
    }
    debugger = shutil.which(gdb)
    provenance["debugger"] = {"command": gdb, "available": debugger is not None}
    if debugger:
        version = context.run([gdb, "--version"], expected=None, timeout=30)
        provenance["debugger"].update({
            "executable_sha256": digest(Path(debugger)),
            "version": version.stdout.splitlines()[0] if version.stdout else "",
            "exit_code": version.returncode,
        })
    try:
        location = context.run(context.startup + ["info", "execution_root"])
        roots = [Path(line.strip()) for line in location.stdout.splitlines() if line.startswith("/")]
        require(roots, "Bazel did not report an execution root")
        query = context.bazel("cquery", "@eros_host_tools//:env_manifest", flags=["--output=files"])
        candidates = [roots[-1] / line.strip() for line in query.stdout.splitlines() if line.startswith("external/")]
        candidates.extend(roots[-1].parents[1] / line.strip() for line in query.stdout.splitlines() if line.startswith("external/"))
        candidates.extend(Path(line.strip()) for line in query.stdout.splitlines() if line.startswith("/"))
        manifest = next(path for path in candidates if path.name == "env_manifest.json" and path.is_file())
        saved = context.evidence / "env_manifest.json"
        shutil.copy2(manifest, saved)
        environment = json.loads(saved.read_text())
        provenance.update({
            "environment_manifest": str(saved),
            "environment_sha256": environment.get("environment_sha256"),
            "sdk": environment.get("sdk"),
            "supported_presets": environment.get("supported_presets"),
        })
    except Exception as error:
        provenance["environment_capture_error"] = f"{type(error).__name__}: {error}"
    return provenance


def save_report(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_path = path if path.suffix == ".json" else path.with_suffix(path.suffix + ".json")
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if path == json_path:
        return
    counts = ", ".join(f"{key}={value}" for key, value in data["counts"].items())
    lines = [
        "# Forge Acceptance Report", "", f"Time: {data['time_utc']}",
        f"Revision: {data['source_revision']} (working tree)", f"Preset: {data['preset']}",
        f"Results: {counts}", f"Complete acceptance: {data['acceptance_complete']}",
        f"Recorded scopes: {len(data['results'])}/{data['expected_scope_count']}; run complete: {data['run_complete']}",
        f"Active scope: {data.get('active_scope') or 'none'}",
        "", data["scope_notice"], "", "| Case | Priority | Status | Scope | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in data["results"]:
        lines.append(f"| {result['id']} | {result['priority']} | {result['status']} | "
                     f"{result['scope']} | {result['evidence']} |")
    lines.extend(["", "## Details", ""])
    for result in data["results"]:
        lines.extend([f"### {result['id']}: {result['status']}", "", result["reason"], ""])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true", help="Run every registered scope, including blockers")
    choice.add_argument("--tc", action="append", metavar="TC-ID", help="Case ID, repeatable; selects all its scopes")
    choice.add_argument("--list", action="store_true", help="List case IDs and scopes without executing")
    parser.add_argument("--preset", default="linux_arm64" if platform.machine() in ("aarch64", "arm64") else "linux_x86_64")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--gdb", default=os.environ.get("FORGE_GDB", "gdb"), help="Debugger executable or isolated debugger wrapper")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--strict", action="store_true", help="Return 2 when SKIP/BLOCKED prevents complete acceptance")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    from acceptance_cases import CASES
    try:
        cases = select_cases(CASES, args.tc or [])
    except ValueError as error:
        parser.error(str(error))
    if not cases:
        parser.error("Empty test selection is not acceptance")
    if args.list:
        for case in cases:
            print(f"{case.id:28} {case.priority} {case.scope}: {case.title}")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = (args.evidence or Path("/tmp/kilo") / f"forge-acceptance-{stamp}").resolve()
    if evidence.is_relative_to(ROOT):
        parser.error("Evidence must be outside the source tree")
    if evidence.exists() and (not evidence.is_dir() or any(evidence.iterdir())):
        parser.error("Evidence directory must be new or empty; previous evidence must not be overwritten")
    evidence.mkdir(parents=True, exist_ok=True)
    source_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False,
    ).stdout.strip()
    output_base = evidence / "bazel-output-base"
    provenance = capture_provenance(evidence, args.preset, args.jobs, output_base, args.gdb)
    results = []
    report = args.report or evidence / "report.md"

    def checkpoint(active_scope=None):
        data = report_data(results, args.preset, source_revision, args.all, len(cases))
        data.update(input_provenance=provenance, active_scope=active_scope)
        save_report(report, data)
        return data

    try:
        for case in cases:
            checkpoint(case.id)
            print(f"RUN     {case.id}: {case.title}", flush=True)
            context = Context(evidence / case.id.replace("/", "_"), args.preset, args.jobs, args.gdb, output_base)
            result = execute(case, context)
            results.append(result)
            print(f"{result.status:7} {result.id}: {result.reason.splitlines()[0]}", flush=True)
            checkpoint()
    finally:
        cleanup = Context(evidence / "cleanup", args.preset, args.jobs, output_base=output_base)
        cleanup.run(cleanup.startup + ["shutdown"], expected=None, timeout=30)
    data = checkpoint()
    print(" ".join(f"{key}={value}" for key, value in data["counts"].items()))
    print(f"Report: {report}\nEvidence: {evidence}")
    if data["counts"]["FAIL"]:
        return 1
    return 2 if args.strict and not data["selected_scopes_passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
