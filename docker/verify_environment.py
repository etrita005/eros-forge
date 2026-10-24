#!/usr/bin/env python3
"""Compare installed image tools with the reviewed local image baseline."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bazel/toolchain"))
import environment


def main():
    lock = json.loads((ROOT / "docker/image.lock.json").read_text())
    spec = json.loads((ROOT / "bazel/toolchain/environment_spec.json").read_text())
    manifest, _ = environment.capture(spec, None, None)
    for name, actual in (
        ("environment_sha256", manifest["environment_sha256"]),
        ("sdk_id", manifest["sdk"]["id"]),
    ):
        if actual != lock[name]:
            raise ValueError(f"Forge image {name} differs from reviewed baseline: {actual}")
    print("Verified Forge image environment " + manifest["environment_sha256"], file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from None
