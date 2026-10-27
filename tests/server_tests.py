"""Server regressions without network, clones or the optional MCP SDK.

Only SDK decorators are stubbed. Jobs, subprocess trees and cache files are real.
The installed SDK/protocol is exercised separately by server_smoke.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from processes import run_process


@contextmanager
def server_fixture():
    class SDK:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, **kwargs):
            return lambda fn: fn

        def custom_route(self, *args, **kwargs):
            return lambda fn: fn

    names = ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.transport_security", "mcp.types")
    modules = {name: ModuleType(name) for name in names}
    modules["mcp.server.fastmcp"].FastMCP = SDK
    modules["mcp.server.transport_security"].TransportSecuritySettings = SimpleNamespace
    modules["mcp.types"].ToolAnnotations = SimpleNamespace
    with tempfile.TemporaryDirectory(prefix="ue-server-") as tmp, \
            patch.dict(os.environ, {"UE_READER_DATA": tmp, "GITHUB_TOKEN": "test-secret-token"}), \
            patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("_ue_test_server", ROOT / "server/server.py")
        server = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: server}):
            spec.loader.exec_module(server)
            yield server


def _run(code, *, timeout=1, lines=None):
    lines = [] if lines is None else lines
    env = dict(os.environ, PYTHONIOENCODING="utf-8:replace")
    return run_process([sys.executable, "-u", "-c", code], env=env, timeout=timeout, on_line=lines.append)


def test_server_deadline_without_output():
    for code in ("import time; time.sleep(120)",
                 "import time; print('unfinished', end='', flush=True); time.sleep(120)",
                 "import os,time; os.close(1); os.close(2); time.sleep(120)",
                 "import os,time\nwhile True: os.write(1, b'x'*4096); time.sleep(.001)"):
        lines = []
        started = time.monotonic()
        try:
            _run(code, timeout=.7, lines=lines)
        except TimeoutError as exc:
            assert "exceeded 0.7s" in str(exc)
        else:
            raise AssertionError("analysis did not time out")
        assert time.monotonic() - started < 6, "deadline blocked on stdout"
        assert all(len(line) <= 4096 for line in lines), "unbounded unterminated line"
    assert not any(t.name == "ue-analysis-output" for t in threading.enumerate()), "pipe reader leaked"


def _is_running(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes as W
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes, api.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        api.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        api.CloseHandle.argtypes = [W.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = W.DWORD()
        try:
            assert api.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            api.CloseHandle(handle)
    # A killed orphan may briefly remain a zombie until its OS reaper collects it.
    status = Path(f"/proc/{pid}/stat")
    if status.exists() and status.read_text(encoding="utf-8").split()[2] == "Z":
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_server_deadline_kills_descendants():
    with tempfile.TemporaryDirectory(prefix="ue-tree-") as tmp:
        pidfile = Path(tmp) / "child.json"
        child = "import time; time.sleep(120)"
        prefix = ("import subprocess,sys,json,os,time; from pathlib import Path; "
                  f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
                  f"Path({str(pidfile)!r}).write_text(json.dumps([os.getpid(),p.pid]),encoding='utf-8'); ")
        # Both a live parent and an exited parent whose child holds stdout open.
        for tail in ("time.sleep(120)", "sys.exit(0)"):
            try:
                _run(prefix + tail, timeout=1.2)
            except TimeoutError:
                pass
            else:
                raise AssertionError("inherited stdout bypassed deadline")
            assert pidfile.is_file(), "fixture did not launch before deadline"
            pids = json.loads(pidfile.read_text(encoding="utf-8"))
            until = time.monotonic() + 3
            while any(_is_running(pid) for pid in pids) and time.monotonic() < until:
                time.sleep(.02)
            assert not any(_is_running(pid) for pid in pids), "descendant survived timeout"
            pidfile.unlink()


def test_server_output_and_exit_status():
    lines = []
    code = "import sys; print('한글 출력'); print('stderr', file=sys.stderr); sys.exit(7)"
    assert _run(code, timeout=5, lines=lines) == 7
    assert "한글 출력" in lines and "stderr" in lines, lines
    assert _run("print('ok')", timeout=5) == 0


def test_server_job_timeout_releases_slot():
    with server_fixture() as server:
        script = Path(server.DATA) / "fake_digest.py"
        script.write_text("import time; print('test-secret-token', flush=True); time.sleep(120)", encoding="utf-8")
        server.DIGEST_SCRIPT, server.JOB_TIMEOUT = script, 1
        repo = server.RepoRef("github.com", "owner", "repo", None)
        job = server.Job("test", "test", repo, "a" * 40, None)
        server.run_job(job)
        assert job.status == "error" and job.done_event.is_set()
        assert "exceeded 1s" in job.error and job.finished is not None
        assert "***" in job.log and "test-secret-token" not in str(job.log)
        assert len(job.log) <= 40
        assert server.RUN_SLOT.acquire(blocking=False), "analysis slot leaked"
        server.RUN_SLOT.release()
        # A following job can run, and a failed exit is not marked done.
        script.write_text("import sys; print('failure'); sys.exit(7)", encoding="utf-8")
        next_job = server.Job("next", "next", repo, "b" * 40, None)
        server.run_job(next_job)
        assert next_job.status == "error" and "digest failed" in next_job.error
