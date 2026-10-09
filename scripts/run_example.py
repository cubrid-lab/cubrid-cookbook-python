#!/usr/bin/env python3
"""run_example.py - Run one command under a wall-clock limit (used by `make verify`).

Portable replacement for GNU ``timeout``: the command runs in its own session
(process group) and inherits stdout/stderr. When the limit expires, the whole
process group is killed, so helper processes cannot keep the output pipe open,
and the runner prints a "run_example: timed out after" marker line to stderr
and exits 124 (the GNU ``timeout`` convention). Otherwise it exits with the
command's own status (128 + N for a signal N). The group is also killed when the
command finishes, so helpers it left behind do not outlive it, and when the
runner itself is interrupted (SIGINT) or receives SIGTERM or SIGHUP (it then
exits 128 + N). POSIX only: it needs process groups.

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
TIMEOUT_MARKER = "run_example: timed out after"


def kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def exit_on_signal(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def run(command: list[str], timeout: float) -> int:
    # SIGTERM/SIGHUP raise SystemExit so the `finally` below reaps the group.
    # All three are held until the child's pid is known, so none can arrive
    # between the fork and the `try`; the child unblocks them before exec.
    held = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, exit_on_signal)
    signal.pthread_sigmask(signal.SIG_BLOCK, held)
    try:
        process = subprocess.Popen(
            command,
            start_new_session=True,
            preexec_fn=lambda: signal.pthread_sigmask(signal.SIG_UNBLOCK, held),
        )
    except BaseException:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, held)
        raise
    try:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, held)
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(process.pid)
        process.wait()
        print(f"{TIMEOUT_MARKER} {timeout:g}s: {' '.join(command)}", file=sys.stderr)
        return TIMEOUT_EXIT
    finally:
        # Also reap helpers a finished (or interrupted) command left behind.
        kill_group(process.pid)
    return 128 - code if code < 0 else code


def main(argv: list[str]) -> int:
    if os.name != "posix":
        print("run_example.py requires POSIX process groups", file=sys.stderr)
        return 2
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
