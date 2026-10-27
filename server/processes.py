"""Run an analysis under a wall-clock deadline and own its entire process tree.

The pipe reader never controls the deadline. Windows uses a gated Job Object;
POSIX uses a new session/process group. Both also remove surviving descendants
after an otherwise successful command.
"""
from __future__ import annotations

import codecs
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


class _WindowsJob:
    def __init__(self):
        import ctypes
        from ctypes import wintypes as W

        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", W.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                        ("active", W.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", W.DWORD), ("scheduling", W.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", Limits), ("io", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [W.LPVOID, W.LPCWSTR], W.HANDLE),
            ("SetInformationJobObject", [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD], W.BOOL),
            ("AssignProcessToJobObject", [W.HANDLE, W.HANDLE], W.BOOL),
            ("TerminateJobObject", [W.HANDLE, W.UINT], W.BOOL),
            ("CloseHandle", [W.HANDLE], W.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, proc):
        import ctypes
        if not self.api.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)
            self.api.CloseHandle(self.handle)
            self.handle = None


def run_process(command: list[str], *, env: dict[str, str], timeout: float,
                on_line: Callable[[str], None]) -> int:
    """Return the exit code; raise TimeoutError even for silent/unbroken output.

    Lines longer than 4096 characters are omitted (never split secret tokens).
    Callback failures are reported to the owner after its process tree is stopped.
    """
    deadline = time.monotonic() + timeout
    job = _WindowsJob() if os.name == "nt" else None
    proc = None
    reader = None
    read_errors = []
    try:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if job else {"start_new_session": True}
        launch = [sys.executable, "-u", str(Path(__file__).with_name("process_gate.py"))] if job else command
        proc = subprocess.Popen(launch, stdin=subprocess.PIPE if job else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, **kwargs)
        if job:
            job.assign(proc)  # the gate cannot spawn anything until this succeeds
            proc.stdin.write((json.dumps(command) + "\n").encode("utf-8"))
            proc.stdin.close()

        def drain():
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            pending = ""
            dropping = False
            try:
                while True:
                    chunk = os.read(proc.stdout.fileno(), 4096)
                    pending += decoder.decode(chunk, final=not chunk)
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        if not dropping:
                            if len(line) > 4096:
                                on_line("[analysis output line exceeds 4096 characters; omitted]")
                            elif line.rstrip():
                                on_line(line.rstrip())
                        dropping = False
                    if len(pending) > 4096:
                        if not dropping:
                            on_line("[analysis output line exceeds 4096 characters; omitted]")
                        dropping = True
                        pending = ""
                    if not chunk:
                        if pending and not dropping:
                            on_line(pending.rstrip())
                        break
            except Exception as exc:
                read_errors.append(exc)

        reader = threading.Thread(target=drain, name="ue-analysis-output", daemon=True)
        reader.start()
        # wait() has its own monotonic timeout; neither readline() nor log volume
        # can postpone it. EOF is also bounded when a descendant inherits stdout.
        try:
            code = proc.wait(timeout=max(0, deadline - time.monotonic()))
            reader.join(timeout=max(0, deadline - time.monotonic()))
            if reader.is_alive():
                raise subprocess.TimeoutExpired(command, timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"analysis exceeded {timeout:g}s") from None
        if read_errors:
            raise RuntimeError(f"analysis output reader failed: {read_errors[0]}")
        return code
    finally:
        if job:
            job.close()
        elif proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc:
            if proc.poll() is None:
                proc.kill()  # includes a gate whose assignment failed
            proc.wait()
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            if reader:
                reader.join(timeout=5)
            if proc.stdout and (not reader or not reader.is_alive()):
                proc.stdout.close()
