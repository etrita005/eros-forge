#!/usr/bin/env python3
"""Expose a single container exec PID to the host signal-forwarding entry."""

import os
from pathlib import Path
import sys


if len(sys.argv) < 3:
    raise SystemExit("Expected PID file and command")

Path(sys.argv[1]).write_text(str(os.getpid()))
os.execv(sys.argv[2], sys.argv[2:])
