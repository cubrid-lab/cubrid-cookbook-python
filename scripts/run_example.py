#!/usr/bin/env python3
"""run_example.py - Run one command under a wall-clock limit (used by `make verify`).

Portable replacement for GNU ``timeout``: the command runs in its own session
(process group) and inherits stdout/stderr. When the limit expires, the whole
process group is killed, so helper processes cannot keep the output pipe open,
and the runner exits 124 (the GNU ``timeout`` convention). Otherwise it exits
with the command's own status (128 + N for a signal N).

Usage:
    python scripts/run_example.py --timeout SECONDS -- COMMAND [ARG ...]
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

TIMEOUT_EXIT = 124


def kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run(command: list[str], timeout: float) -> int:
    process = subprocess.Popen(command, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(process.pid)
        process.wait()
        print(f"run_example: timed out after {timeout:g}s: {' '.join(command)}", file=sys.stderr)
        return TIMEOUT_EXIT
    finally:
        # Also reap helpers a finished (or interrupted) command left behind.
        kill_group(process.pid)
    return 128 - code if code < 0 else code


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.timeout <= 0:
        parser.error("needs a positive --timeout and a command")
    return run(command, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
